"""Request/response logging, and the guarantee that no traceback escapes.

The middleware is the application's outermost boundary in both directions: it
logs what came in, logs what went out, and catches whatever neither the view
nor Django handled. The tests that matter most here are the negative ones —
what the browser *does not* receive when something goes wrong.
"""

import json
import logging
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from image_gallery.logging import JsonFormatter
from image_gallery.provider import UpstreamError


def url_for(image_id: int) -> str:
    return reverse("image", args=[image_id])


def messages(caplog, name: str) -> list[str]:
    return [r.message for r in caplog.records if r.name == name]


def record_for(caplog, message: str) -> logging.LogRecord:
    """The single record with this message, failing loudly if absent."""
    matches = [r for r in caplog.records if r.message == message]
    assert matches, f"no {message!r} record in {[r.message for r in caplog.records]}"
    return matches[0]


# --- both ends of a request ---------------------------------------------


def test_a_request_and_its_response_are_both_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger="gallery.request"):
        client.get(reverse("index"))

    assert messages(caplog, "gallery.request") == ["request", "response"]


def test_the_request_line_carries_the_query_string(client, caplog):
    """The query string is the whole input surface — a log without it cannot
    explain what was asked for."""
    with caplog.at_level(logging.INFO, logger="gallery.request"):
        client.get(reverse("index"), {"count": "10", "grayscale": "1"})

    record = record_for(caplog, "request")
    assert record.method == "GET"
    assert record.path == reverse("index")
    assert "count=10" in record.query
    assert "grayscale=1" in record.query


def test_the_response_line_carries_status_and_duration(client, caplog):
    with caplog.at_level(logging.INFO, logger="gallery.request"):
        client.get(reverse("index"))

    record = record_for(caplog, "response")
    assert record.status == 200
    assert isinstance(record.duration_ms, float)


def test_both_lines_share_one_request_id(client, caplog):
    """Tiles are fetched concurrently, so lines from a dozen requests
    interleave. The id is what makes one request greppable as a unit."""
    with caplog.at_level(logging.INFO, logger="gallery.request"):
        client.get(reverse("index"))

    request_line = record_for(caplog, "request")
    response_line = record_for(caplog, "response")
    assert request_line.request_id == response_line.request_id


def test_separate_requests_get_separate_ids(client, caplog):
    with caplog.at_level(logging.INFO, logger="gallery.request"):
        client.get(reverse("index"))
        client.get(reverse("index"))

    ids = {r.request_id for r in caplog.records if r.message == "request"}
    assert len(ids) == 2


# --- levels reflect what happened ---------------------------------------


def test_a_server_error_is_logged_at_error(client, caplog):
    with caplog.at_level(logging.DEBUG, logger="gallery.request"):
        with patch(
            "image_gallery.views.image.ImageProxyView._serve",
            side_effect=RuntimeError("boom"),
        ):
            client.get(url_for(1))

    assert record_for(caplog, "request failed").levelno == logging.ERROR


def test_a_client_error_is_logged_at_warning(client, caplog):
    """A 404 is not a system failure, but it is not routine traffic either."""
    with caplog.at_level(logging.DEBUG, logger="gallery.request"):
        client.get(url_for(99999))

    assert record_for(caplog, "response").levelno == logging.WARNING


def test_a_404_stays_a_404(client):
    """`Http404` is how a view says "no such image", not a fault report.

    An earlier version of this middleware caught it like any other exception
    and answered 500, turning every out-of-catalogue id into a server error.
    Django's control-flow exceptions have to reach their own handlers.
    """
    response = client.get(url_for(99999))

    assert response.status_code == 404


def test_a_404_is_not_logged_as_a_failure(client, caplog):
    with caplog.at_level(logging.DEBUG, logger="gallery.request"):
        client.get(url_for(99999))

    assert "request failed" not in messages(caplog, "gallery.request")


def test_the_health_check_is_quiet(client, caplog):
    """Polled every 30s forever. At INFO it would rebuild exactly the noise
    that removing gunicorn's access log was meant to end."""
    with caplog.at_level(logging.INFO, logger="gallery.request"):
        client.get(reverse("healthz"))

    assert messages(caplog, "gallery.request") == []


def test_the_health_check_is_still_logged_at_debug(client, caplog):
    with caplog.at_level(logging.DEBUG, logger="gallery.request"):
        client.get(reverse("healthz"))

    assert messages(caplog, "gallery.request") == ["request", "response"]


def test_a_failing_health_check_is_never_quiet(client, caplog):
    """Being on the quiet list must not hide the endpoint actually breaking."""
    with caplog.at_level(logging.INFO, logger="gallery.request"):
        with patch(
            "image_gallery.views.health.HealthView.get",
            side_effect=RuntimeError("down"),
        ):
            client.get(reverse("healthz"))

    assert "request failed" in messages(caplog, "gallery.request")


# --- the response line explains itself -----------------------------------


def test_the_image_source_tier_is_logged(client, caplog):
    """Turns a wall of identical 200s into something that shows cache
    behaviour at a glance."""
    with caplog.at_level(logging.INFO, logger="gallery.request"):
        with patch(
            "image_gallery.views.image.PicsumProvider.fetch",
            side_effect=UpstreamError("down"),
        ):
            client.get(url_for(1))

    assert record_for(caplog, "response").image_source == "placeholder"


def test_a_redirect_logs_where_it_sends_the_user(client, caplog):
    """The shell corrects bad URLs by redirecting; this is what makes that
    correction traceable."""
    with caplog.at_level(logging.INFO, logger="gallery.request"):
        client.get(reverse("index"), {"size": "huge"})

    assert "notice=invalid_size" in record_for(caplog, "response").location


# --- nothing leaks to the browser ----------------------------------------


@override_settings(DEBUG=True)
def test_no_traceback_reaches_the_browser_even_with_debug_on(client, caplog):
    """The whole point of catching here rather than trusting configuration.

    With `DEBUG=True` Django renders its traceback page to whoever asked. The
    middleware's catch does not consult DEBUG, so the leak is closed by code
    rather than by an environment variable someone might flip.
    """
    with caplog.at_level(logging.ERROR, logger="gallery.request"):
        with patch(
            "image_gallery.views.shell.AppShellView.get",
            side_effect=RuntimeError("secret internal detail"),
        ):
            response = client.get(reverse("index"))

    assert response.status_code == 500
    body = response.content.decode()
    assert "secret internal detail" not in body
    assert "Traceback" not in body
    assert "RuntimeError" not in body


def test_the_error_body_carries_only_a_request_id(client, caplog):
    """Enough for a user to quote when reporting a failure, and nothing that
    describes the failure itself."""
    with caplog.at_level(logging.ERROR, logger="gallery.request"):
        with patch(
            "image_gallery.views.shell.AppShellView.get",
            side_effect=RuntimeError("boom"),
        ):
            response = client.get(reverse("index"))

    payload = json.loads(response.content)
    assert payload == {
        "error": "internal_error",
        "request_id": record_for(caplog, "request failed").request_id,
    }


def test_a_crashing_image_endpoint_returns_empty_bytes(client):
    """An <img> cannot read JSON and cannot show a message. An empty body is
    what fires its `error` event, which is what marks the tile failed and feeds
    the degraded-count banner — the same signal the 504 tier already uses."""
    with patch(
        "image_gallery.views.image.ImageProxyView._serve",
        side_effect=RuntimeError("boom"),
    ):
        response = client.get(url_for(1))

    assert response.status_code == 500
    assert response.content == b""


# --- the traceback goes to the log, and only there -----------------------


def test_the_traceback_is_logged(client, caplog):
    with caplog.at_level(logging.ERROR, logger="gallery.request"):
        with patch(
            "image_gallery.views.shell.AppShellView.get",
            side_effect=RuntimeError("secret internal detail"),
        ):
            client.get(reverse("index"))

    record = record_for(caplog, "request failed")
    assert record.exc_info is not None
    assert record.error == "RuntimeError"
    assert "secret internal detail" in JsonFormatter().format(record)


def test_the_logged_traceback_is_still_one_line_of_json(client, caplog):
    """A traceback is the most newline-heavy thing this application logs. If
    anything breaks the one-line-per-record contract, it is this."""
    with caplog.at_level(logging.ERROR, logger="gallery.request"):
        with patch(
            "image_gallery.views.shell.AppShellView.get",
            side_effect=RuntimeError('quotes " and \\ backslash'),
        ):
            client.get(reverse("index"))

    formatted = JsonFormatter().format(record_for(caplog, "request failed"))

    assert "\n" not in formatted
    assert "Traceback" in json.loads(formatted)["exception"]


def test_django_does_not_also_report_the_exception(client, caplog):
    """Django logs unhandled exceptions to `django.request` with its own
    traceback. The middleware has already logged it with the request context
    attached, so leaving that logger enabled would emit every failure twice."""
    with caplog.at_level(logging.DEBUG):
        with patch(
            "image_gallery.views.shell.AppShellView.get",
            side_effect=RuntimeError("boom"),
        ):
            client.get(reverse("index"))

    assert messages(caplog, "django.request") == []
