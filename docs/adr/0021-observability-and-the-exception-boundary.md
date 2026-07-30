# 21. Requests are logged at the edge, where exceptions also stop

## Context

Container output was gunicorn's access log: one Apache-style line per HTTP
request. Because [ADR 17](0017-image-fetch-timing.md) makes each tile its own
request, a single default page load produced fifty-odd lines, and the
`HEALTHCHECK` added one every thirty seconds forever. The signal-to-noise ratio
was bad enough that `docker compose logs` was not worth reading — which is the
condition [the E2E lesson](../../tests/README.md) warns about, where a real
failure sits in the stream unnoticed.

Removing the access log fixed the noise and left a gap. Nothing recorded what
was asked for, which cache tier answered, what the application sent upstream,
or what came back. The tiering of [ADR 12](0012-resilience-strategy.md) makes
that gap worse than it sounds: a degraded page and a healthy one both return
`200`, so without logs there is no way to tell a fully-served grid from one
quietly running on stale bytes.

Separately, nothing structurally prevented a stack trace reaching a browser.
`DEBUG` defaults to `False`, so in practice none did — but that is a
configuration promise. `DJANGO_DEBUG=1` in the wrong environment turns every
unhandled exception into a page rendering source, local variables, and settings
to whoever sent the request.

## Decision

**One middleware logs both ends of every request and is the last place an
exception can be caught.**

Not per-view `try` blocks. A `try` in a view protects that view, and the cases
that actually leak are the ones no view can see: a template failing to render,
a middleware below raising, a response object blowing up after the view
returned cleanly. Views that do not exist yet are covered for free.

**The catch does not consult `DEBUG`.** It is `process_exception`, not an
`except` around `get_response`, because Django converts an exception into a
response *inside* `get_response` — by the time an `except` there sees anything,
the debug traceback page has already been built. Hooking earlier means the page
is never built rather than suppressed by a setting. The traceback goes to the
log through `logger.exception`, the client gets a body chosen by endpoint type,
and no code path joins the two.

**Django's control-flow exceptions pass through.** `Http404`,
`PermissionDenied`, `BadRequest`, and `SuspiciousOperation` are how a view
*names a status code*, not how it reports a fault. Catching them like faults
turned every out-of-catalogue id into a `500` — caught by a test, and the
reason `_PASS_THROUGH` exists.

**The error body is shaped by the caller.** An `<img>` cannot read JSON and
cannot display a message, so bytes endpoints get an empty body: the only thing
that fires the element's `error` event, which is what marks a tile failed and
feeds the degraded count. That is the same signal the `504` placeholder tier
already uses, so the client needed no change. Everything else gets JSON
carrying a request id and nothing describing the failure.

**Application logs are levelled separately from Django's.** `gallery.*` reads
`GALLERY_LOG_LEVEL`, so the useful setting — quiet the framework, keep ours —
is one variable. `django.request` is silenced because the middleware has
already logged the same exception with request context attached.

**The health endpoint is DEBUG.** It is polled forever; at INFO it rebuilds
exactly the noise this ADR removed. A `4xx`/`5xx` from it is still logged at
its own level, so a broken health check cannot hide behind that.

## Consequences

`docker compose logs` after a page load now shows the request, each upstream
call with its URL, byte count and duration, the tier that answered, and the
response — correlated by a request id, since concurrent tiles interleave. The
`image_source` field makes a cache hit visible as data rather than as an
inference from a suspiciously fast response.

Per-request logging is genuinely more volume than the access log it replaced —
the e2e run emits ~2,500 request lines. It is structured, correlated, and
levelled, so it filters; the access log did not. `GALLERY_LOG_LEVEL=WARNING`
reduces it to failures only if that volume becomes a problem.

Cache hit/miss detail sits at DEBUG deliberately. It is per-lookup and would
double the line count at INFO for information that only matters when
investigating cache behaviour specifically.

The exception boundary is now testable, and tested: `DEBUG=True` plus a
raising view asserts on the absence of the traceback, the exception text, and
the class name in the response body.

## Alternatives considered

**A base view class wrapping `dispatch`.** Rejected: a new view that forgets to
inherit it is silently unprotected, and errors outside `dispatch` still escape.
The failure mode is invisible, which is the wrong failure mode for a boundary.

**Trusting `DEBUG=False`.** It is what Django intends and it does work. But it
makes "no traceback reaches a user" a property of the environment rather than
of the code, and the cost of not relying on it turned out to be one hook.

**Gunicorn's access log with a filter.** Would have kept per-request lines
without application context — no cache tier, no upstream timing, no request id
tying a tile to its fetch. The noise was the visible problem; the missing
context was the real one.
