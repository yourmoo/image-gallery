# 3. Django proxies image bytes

## Context

The obvious implementation puts a picsum.dev URL in the `src` of each `<img>`
and lets the browser fetch it. It is simpler, it offloads bandwidth, and it is
what most gallery tutorials do.

Two brief requirements make it the wrong choice here:

- **Line 81** — "downloaded upstream images must be cached while the app is
  running". If the browser fetches directly, the application never downloads
  anything and there is nothing for it to cache. The requirement would be
  unsatisfiable as written.
- **Lines 77–78** — all image generation logic on the backend, and templates
  must not construct image URLs. A picsum URL in a template is the template
  constructing an image URL.

There is also a design argument the brief gestures at in line 91: the provider
should be replaceable with minimal changes. A provider URL reaching the browser
is a provider detail escaping into the client.

## Decision

Django is an image proxy. Templates emit `<img src="/images/47?size=large">`
pointing at Django; Django fetches from picsum.dev, applies the transformation
logic, and serves the bytes.

**The browser never learns the provider exists.** No picsum.dev URL appears in
any template, response body, or rendered HTML.

## Consequences

**Caching means image bytes, not metadata.** This is the consequence that
matters most, and it invalidated an earlier sizing analysis that had assumed
metadata-only payloads of roughly 1.4 KB per page. Measured against picsum.dev
across eight seeds per dimension on 2026-07-28 — sizes vary 2–3× with image
content, so the median matters more than any single sample:

| Size | Median | Max | Per 10-image page (median) |
| --- | --- | --- | --- |
| small (200×200) | ~7.8 KB | ~14.7 KB | ~78 KB |
| medium (400×400) | ~20.8 KB | ~41 KB | ~208 KB |
| large (800×800) | ~59.4 KB | ~114.5 KB | ~594 KB |

A large page is roughly **400× the original assumption**. The variation space is
`id × 3 sizes × 2 grayscale × 11 blur` = 66 variants per image, so the full
named-size key space for a 100-image catalogue is ~222 MB at mean sizes. See
[ADR 11](0011-cache-sizing.md) for how the cache is bounded against that.

**The existing cache configuration is not adequate for this.** `MAX_ENTRIES`
counts entries rather than bytes, so 1000 entries of large images is roughly
68 MB per worker and ~205 MB at the dimension ceiling. Per-process caching also
means a worker-local miss costs a real upstream fetch, roughly doubling upstream
traffic across two workers. [ADR 11](0011-cache-sizing.md) settles the sizing —
including the measurement showing that a third suspected problem, pickle
overhead on JPEG byte strings, is not real.

**Transformations are passed through, not applied locally.** Django forwards the
transformation to the provider and serves the result; it does not fetch a base
image and apply grayscale or blur itself. picsum performs these natively,
deterministically, and for free, and the provider's own output at each size is
smaller than downscaling a large original would be — serving a 6.6 KB small
image from a cached 44 KB large one would spend both bandwidth and CPU to
produce something the provider already returns. Adding an image-processing
dependency to reimplement transformations the provider performs correctly was
rejected on that basis. "Backend logic" (line 77) is satisfied by the
application owning translation, orchestration, validation, and caching — see
[ADR 9](0009-url-vocabularies.md).

**Every image is a request through Django.** A 50-image page is 50 proxied
requests. This is what makes the per-image loading placeholder necessary
([ADR 2](0002-client-side-rendering.md)) and what makes concurrency behaviour
worth validating (brief line 148).

**The provider becomes replaceable.** Swapping picsum.dev for another source
changes one service-layer component and no templates, which is what line 91
asks for.

**Upstream failures become the application's problem**, not the browser's. That
is a cost, but it is also precisely what the brief's resilience requirements
(lines 105–128) ask the application to own.

## Alternatives rejected

**Direct browser-to-picsum URLs.** Simplest, and offloads bandwidth. Rejected
because it makes line 81 unsatisfiable and puts provider URLs in templates,
violating line 78.

**Proxy metadata only, browser fetches images.** A middle position where Django
returns image URLs the browser then fetches. Fails the same two requirements —
the URL still reaches the browser and the application still downloads nothing.

**Redirect to picsum from a Django URL.** `/images/47` returning a 302 to
picsum keeps provider URLs out of templates but still exposes them to the
browser, still downloads nothing, and adds a round trip.
