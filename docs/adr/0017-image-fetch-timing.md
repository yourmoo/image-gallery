# 17. Images are fetched when the browser requests them

## Context

A gallery page is one `GET /api/images` call returning metadata for N images,
followed by N `<img src="/images/{id}">` requests as the browser renders the
grid. That much follows from [ADR 2](0002-client-side-rendering.md).

What was never decided is **when the upstream fetches happen**, and the question
had gone unnoticed because `tests/features/gallery.feature` asserted only that
ten upstream calls occur — not when.

Two designs satisfy that assertion:

**Prefetch.** `/api/images` fans out to picsum for all N images before
responding. One browser call, N upstream calls, and the JSON arrives only after
the slowest fetch completes.

**On demand.** `/api/images` returns immediately from request parameters alone.
Each `/images/{id}` fetches its own bytes when the browser asks. N+1 browser
calls, N upstream calls, and the grid is on screen before any of them finish.

The deciding observation is that **`/api/images` has nothing to learn from
upstream**. Every field in the response — `id`, `url`, `width`, `height`,
`grayscale`, `blur` — is derived from the request and from configuration. Ids
come from page arithmetic, `url` is a reversed route, and the dimensions are the
resolved `size` parameter. picsum.dev has no metadata endpoint
([ADR 9](0009-url-vocabularies.md)); it returns JPEG bytes and nothing else.

Prefetching would therefore make the metadata call wait on ten fetches whose
results it does not use, purely to warm the cache for the requests that follow.

## Decision

**Image bytes are fetched by `/images/{id}`, one request per image, when the
browser asks for it. Nothing fetches them earlier.**

> **Amended 2026-07-29.** This ADR was written when a `/api/images` metadata
> endpoint preceded those requests, and its reasoning below is phrased in terms
> of that call. The endpoint has since been removed — the observation that it
> had nothing to learn from upstream was followed to its conclusion, and the
> client now derives the id range from bounds the shell publishes
> ([ADR 20](0020-ids-are-derived-in-the-browser.md)). **The decision this ADR
> makes is unaffected**: fetch timing, per-tile failure, and the concurrency
> analysis all concern `/images/{id}`, which is unchanged. Read "the metadata
> call" below as "the document request".

### The unit of fan-out changes

The application still issues N upstream calls per page, but they arrive as N
independent HTTP requests rather than one request fanning out internally. This
is what [ADR 14](0014-concurrency-validation.md) now records: parallelism comes
from the browser's own connection pool, not from a server-side
`ThreadPoolExecutor`.

### Failure is reported by the tile, not by the page

[ADR 12](0012-resilience-strategy.md)'s three tiers are unchanged — fresh,
stale, placeholder — but the tier is now resolved per `/images/{id}` request
rather than during page assembly. A failing image cannot be mentioned in the
`/api/images` response, because that response was sent before the fetch was
attempted.

The degraded banner is therefore assembled **client-side**: the grid counts
tiles that failed to load and renders the notice itself. Parameter substitution
is a separate mechanism that produces a similar-looking banner — it is known
before the metadata call and travels through the `index` redirect's `?notice=`
([ADR 19](0019-validation-errors-carry-a-usable-payload.md)), not through this
payload.

## Consequences

**The grid renders immediately, regardless of upstream.** The page is on screen
after one fast local call. Images fill in progressively. A picsum outage
degrades tiles; it never delays or blocks the page — which is the strongest
form of the resilience property brief lines 105–128 ask for.

**`GALLERY_FETCH_CONCURRENCY` no longer governs a thread pool.** Nothing in
Django fans out, so there is no pool to size. The setting is removed. See
[ADR 14](0014-concurrency-validation.md), amended.

**Concurrency is now `min(browser connection limit, gunicorn request slots)`,
and the second term is ours to get right.** The browser allows 6 connections per
origin over HTTP/1.1. Gunicorn must stay above that or it becomes the binding
constraint and re-serialises the page — the failure mode this ADR was written to
avoid. The default sync worker serves one request per process, so `--workers 2`
alone would fetch a 10-image page 2 at a time: five waves of ~450 ms, ~2.2 s,
most of the way back to the serial timings in
[ADR 14](0014-concurrency-validation.md).

The Dockerfile therefore runs `gthread` with `--workers 2 --threads 8` — 16
slots. The work is blocking I/O, so threads are the right primitive and the GIL
is not a constraint; this is the same argument ADR 14 made for its pool, applied
to the request path instead. **This is a real coupling: raising the page-size
allow-list or deploying with different worker settings changes fetch
concurrency.**

**A 50-image page is bounded by the browser, not by us.** Six-at-a-time is
slower per-image than a ten-worker pool would have been, but no user waits on it
— tiles appear as they arrive rather than all at once after the slowest. HTTP/2
removes the 6-connection cap entirely by multiplexing, so a TLS-terminating
proxy in front of gunicorn closes the gap without any application change.

**Loading state becomes a real UI state.** A tile now has three visible
conditions rather than two: loading, loaded, failed. The design system already
requires that failure and loading not look alike
([ADR 12](0012-resilience-strategy.md)); on-demand fetching makes the loading
state long enough to actually see.

**The timeout scenario changes meaning.** "A slow gallery does not hold the page
open indefinitely" was previously about bounding a server-side page assembly.
It is now trivially true — nothing holds the page open — and the scenario
asserts the grid appears *before* the images.

**Two round trips before the first pixel.** `/api/images` then `/images/1`,
where prefetch would have needed one. The first is local and fast, so the
practical cost is small, but it is a real added hop.

**The cache is still warmed the same way.** `/images/{id}` reads and writes the
same `LocMemCache` entries ([ADR 11](0011-cache-sizing.md)); only the caller
changed. A second visit to a page still produces zero upstream traffic.

## Alternatives rejected

**Prefetch on the metadata call.** One browser round trip, and the server knows
every image's fate before responding — which would let the degraded banner be
computed server-side, where the rest of the notice logic already lives.
Rejected because it makes a metadata response that needs no upstream data wait
on ten upstream fetches: ~450 ms cold at ten workers, and the full
`GALLERY_UPSTREAM_TIMEOUT` when upstream hangs. It ties a fast local call to the
health of a remote service for no informational gain, and it contradicts
[ADR 2](0002-client-side-rendering.md)'s reason for rendering client-side.

**Prefetch asynchronously — respond immediately, warm the cache in a background
thread.** Keeps the fast response and still populates the cache before the
browser asks. Rejected because the browser's requests race the warming thread,
so each image is either a hit or a duplicate in-flight fetch — the stampede of
[ADR 14](0014-concurrency-validation.md) with extra machinery. It also
reintroduces a thread pool whose lifecycle must outlive the request.

**Serve the bytes inline as data URIs in the metadata JSON.** One round trip for
the whole grid, which sidesteps both the browser's 6-connection cap and the
gunicorn slot count above. Reconsidered on 2026-07-29 and measured against
picsum at 400×400:

| | Value |
| --- | --- |
| 10 images, raw | 204 KB |
| 10 images, base64 | **272 KB** (+33%) |
| Fetch, serial | 4271 ms |

Rejected on two counts. **Nothing renders until the last byte arrives** — a
single response cannot paint progressively, so the user sees a blank grid for
the entire fetch (~800 ms threaded, 4.3 s serial, several seconds at
`count=50`), against ~20 ms for a metadata call that makes no upstream request.
**Browser image caching is lost entirely**: a data URI inside a JSON body is not
a cacheable resource, so paging away and back refetches every image, where
distinct `/images/{id}` URLs are cached by the browser for free.

It also does not remove the second endpoint. Changing a filter on one image
needs `/images/{id}` regardless, so this buys a second code path — a base64
encoder alongside the byte proxy — rather than replacing one.

**Inline data URIs at `small` only.** A narrower version: ~88 KB base64 for ten
small images is a defensible payload, and the size parameter would select the
transport. Rejected because it makes load behaviour depend on a display
parameter, and keeps both code paths permanently to save one round trip on the
cheapest case.
