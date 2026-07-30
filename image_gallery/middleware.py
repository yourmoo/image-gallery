"""Request/response logging, and the last place an exception can be caught.

Two jobs in one middleware because they are the same job seen from either end:
every request that enters gets a line, and every request that leaves gets a
line — whether it leaves through a view's `return` or through an exception.
Splitting them would mean two wrappers around the same call, and the failure
path would have to be written twice.

**Why here and not in the views.** A `try` in each view protects that view.
This protects the ones nobody has written yet, plus the errors no view can
see: a template that fails to render, middleware below this one raising, a
`__call__` on a response object blowing up after the view returned cleanly.
Those never reach a view's `except`, and they are exactly the cases where a
stack trace would otherwise reach the browser.

**Why the browser never gets a trace.** `DEBUG=False` already suppresses
tracebacks, but that is a configuration promise: set `DJANGO_DEBUG=1` and
Django will happily render its yellow traceback page to whoever asked. The
catch here does not consult `DEBUG`. The traceback goes to the log stream via
`logger.exception`, the client gets a body chosen by endpoint type, and there
is no code path that puts the two together.

The health endpoint is logged at DEBUG rather than INFO. The container health
check hits it every 30s forever, and at INFO it reproduces the per-request
noise that removing gunicorn's access log was meant to end.
"""

from __future__ import annotations

import logging
import time
import uuid

from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpResponse, JsonResponse
from django.urls import reverse

logger = logging.getLogger("gallery.request")

# Exceptions Django raises to *mean* a status code rather than to report a
# fault. Each already has a handler that renders the right response, so this
# middleware logs the outcome as a normal 4xx and stays out of the way.
_PASS_THROUGH = (Http404, PermissionDenied, BadRequest, SuspiciousOperation)

# Paths whose request/response pair is logged at DEBUG. Polled endpoints only:
# anything a human or a browser actually navigates to belongs at INFO.
_QUIET_PATHS = frozenset({"/healthz"})


def _is_bytes_endpoint(path: str) -> bool:
    """Whether this path serves image bytes rather than a document.

    Derived from the route rather than written as a literal, per the URL
    contract in urls.py: reverse a representative id and keep the prefix, so
    moving the route moves this with it.
    """
    return path.startswith(reverse("image", args=[1]).rsplit("/", 1)[0] + "/")


class RequestLoggingMiddleware:
    """Log both ends of every request, and let no exception past."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = uuid.uuid4().hex[:12]
        # Attached so downstream code — and the exception path below — can put
        # the same id on its own lines. One request's logs are greppable as a
        # unit, which matters when tiles are being fetched concurrently and
        # lines from a dozen requests interleave.
        request.request_id = request_id

        level = logging.DEBUG if request.path in _QUIET_PATHS else logging.INFO
        # Stashed on the request so `process_exception` — a separate entry
        # point Django calls directly — can still report how long the request
        # ran before it failed.
        started = request._started_at = time.monotonic()

        logger.log(
            level,
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                # The query string is the whole input surface of this
                # application — every parameter that changes an image is in
                # here, so a log without it cannot explain what was asked for.
                "query": request.META.get("QUERY_STRING", ""),
            },
        )

        try:
            response = self.get_response(request)
        except Exception as exc:
            # Reached only for exceptions raised *outside* the view — by a
            # middleware below this one, say. A view's exception is handled by
            # `process_exception` before it ever gets here.
            self._log_exception(request, request_id, exc, started)
            return self._safe_error(request, request_id)

        duration_ms = round((time.monotonic() - started) * 1000, 1)
        # A handled failure is still a failure worth seeing. 5xx goes to ERROR
        # and 4xx to WARNING even on a quiet path, so a broken health check
        # does not stay invisible at DEBUG.
        if response.status_code >= 500:
            response_level = logging.ERROR
        elif response.status_code >= 400:
            response_level = logging.WARNING
        else:
            response_level = level

        extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        }

        # Which tier answered, when the image proxy set it. Turns a wall of
        # identical 200s into something that shows cache behaviour at a glance.
        source = response.headers.get("X-Image-Source")
        if source:
            extra["image_source"] = source
        # Where a redirect is sending them. The shell corrects bad URLs by
        # redirecting, so this is how that correction is traceable.
        location = response.headers.get("Location")
        if location:
            extra["location"] = location

        logger.log(response_level, "response", extra=extra)
        return response

    def process_exception(self, request, exception):
        """Where a view's exception is actually caught.

        Django calls this *before* it converts an exception into a response,
        which is the only hook that runs early enough to matter. By the time
        `get_response` returns to `__call__` above, Django has already turned
        the exception into either a 500 page or — with `DEBUG=True` — a full
        traceback page, and the `except` there never sees it.

        Returning a response from here replaces Django's, so the debug page is
        not merely suppressed by configuration: it is never built.
        """
        # Django's control-flow exceptions are not failures: `Http404` is how a
        # view says "no such image" and `PermissionDenied` is a deliberate
        # refusal. Returning a response for these would turn every 404 in the
        # application into a 500 — returning None hands them back to Django's
        # own handlers, which render the right status.
        if isinstance(exception, _PASS_THROUGH):
            return None

        request_id = getattr(request, "request_id", "unknown")
        self._log_exception(
            request, request_id, exception, getattr(request, "_started_at", None)
        )
        return self._safe_error(request, request_id)

    @staticmethod
    def _log_exception(request, request_id: str, exc: Exception, started) -> None:
        """The traceback's one destination.

        `.exception` attaches it to the record, and the JSON formatter puts it
        in the object's "exception" key — so even a multi-line traceback stays
        one parseable line rather than spilling newlines into the stream.
        """
        extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "query": request.META.get("QUERY_STRING", ""),
            "error": type(exc).__name__,
        }
        if started is not None:
            extra["duration_ms"] = round((time.monotonic() - started) * 1000, 1)

        logger.exception("request failed", extra=extra, exc_info=exc)

    @staticmethod
    def _safe_error(request, request_id: str) -> HttpResponse:
        """A response that says something went wrong and nothing about what.

        Shaped by what the caller is: an `<img>` element cannot read JSON and
        cannot show an error message, so bytes endpoints get an empty body
        whose only job is to fire the element's `error` event — the same signal
        the 504 placeholder tier already uses, which the client counts as a
        degraded tile. Everything else gets JSON carrying the request id, so a
        user reporting a failure can quote a string that appears in the logs.

        No exception text, no class name, no path detail in any branch.
        """
        if _is_bytes_endpoint(request.path):
            # Empty body, so nothing decodes and `error` fires. A renderable
            # body here would have the tile style itself as loaded — the same
            # reasoning as the placeholder tier in views/image.py.
            return HttpResponse(b"", content_type="image/gif", status=500)

        return JsonResponse(
            {"error": "internal_error", "request_id": request_id}, status=500
        )
