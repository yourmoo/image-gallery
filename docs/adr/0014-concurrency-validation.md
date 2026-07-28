# 14. Parallel image fetching, and the stampede we are accepting

> **Amended by [ADR 17](0017-image-fetch-timing.md).** The outgoing fan-out
> section below decided that Django fetches a page's N images in a bounded
> `ThreadPoolExecutor`. ADR 17 removed the server-side fan-out entirely: each
> image is fetched by its own `/images/{id}` request, so parallelism comes from
> the browser's connection pool and `GALLERY_FETCH_CONCURRENCY` no longer
> exists.
>
> **The measurements below stand** — they are picsum round-trip latencies, and
> they are what makes serial-per-page unviable and therefore what motivated
> ADR 17's per-request model. Read the fan-out decision as superseded and the
> numbers as current. **The incoming-contention half is unaffected**: the
> stampede is a property of the cache, not of who calls it, and concurrent cold
> requests for one image still produce one upstream call each.

There are two distinct concurrency concerns in this application, and an earlier
version of this record addressed only the second:

1. **Outgoing fan-out** — a page needs N images, so it makes N upstream calls.
   Serially this is unusably slow. *Superseded by ADR 17 — see the note above.*
2. **Incoming contention** — several clients requesting the same uncached image
   at once. This is a measurement and an accepted limitation.

## Context

Brief line 148 asks for "a lightweight concurrency validation approach (for
example, repeated concurrent gallery requests)" and, notably, to "describe
observed cache behaviour". The requirement is to *measure and report*, not
merely to have a passing test.

Line 141 separately requires preventing "duplicate upstream calls for repeated
equivalent requests".

Those two are in tension in a way that only shows up under concurrency, so the
behaviour was measured before deciding anything.

## Measurements — outgoing fan-out

Real fetches against picsum.dev, cold, at 400×400.

| Page | Mode | Wall clock |
| --- | --- | --- |
| 10 images | Serial | **3769 ms** |
| 10 images | Parallel, 5 workers | 907 ms (4.2×) |
| 10 images | Parallel, 10 workers | **454 ms (8.3×)** |
| 50 images | Serial (extrapolated) | ~18900 ms |
| 50 images | Parallel, 10 workers | 2496 ms |
| 50 images | Parallel, 16 workers | **1383 ms** |

Serial fetching is not a slow implementation of a working design; it is an
unusable one. A cold 50-image page would take roughly **19 seconds**, well past
any reasonable timeout and past the point a user waits.

## Measurements — incoming contention

A cache round trip with a 150 ms stand-in for an upstream fetch, against the
configured `LocMemCache`.

**Concurrent requests for the same uncached image:**

| Threads on one key | Upstream calls | Ideal |
| --- | --- | --- |
| 8 | **8** | 1 |

**Five users loading a cold page 1 (10 images) simultaneously:**

| Cache state | Upstream calls | Wall clock |
| --- | --- | --- |
| Cold | **50** (ideal 10) | 1510 ms |
| Warm | **0** | 3.1 ms |

The warm result is the requirement working exactly as intended: repeated
equivalent requests produce no upstream traffic at all, and the page assembles
in ~3 ms.

The cold result is a **cache stampede**. Django's cache API has no request
coalescing: `get()` returning `None` and the subsequent `set()` are separate
operations, so every concurrent miss on the same key performs its own fetch.
Five simultaneous cold loads of the same page produce 5× the necessary upstream
traffic.

## Decision

### Images on a page are fetched in parallel

> **Superseded by [ADR 17](0017-image-fetch-timing.md).** There is no
> server-side fan-out: `/api/images` performs no upstream I/O, and each image is
> fetched by its own request. The paragraphs in this subsection describe a thread
> pool that is not built. What survives is the *reason* for it — serial fetching
> of a page is unviable — which ADR 17 satisfies by letting the browser issue the
> requests in parallel instead.

`gallery.py` fetches a page's images concurrently through a bounded
`ThreadPoolExecutor`, sized by `GALLERY_FETCH_CONCURRENCY` (default 10). The
work is pure I/O wait, so threads are the right primitive and the GIL is not a
constraint.

**The pool is bounded, and the bound is not the page size.** Fifty simultaneous
connections to one host is impolite to the provider and exhausts local sockets
under load. Ten workers already recovers most of the benefit — 8.3× on a
10-image page — and a 50-image page completes in ~2.5 s rather than ~19 s.

**Per-image failure is isolated.** [ADR 12](0012-resilience-strategy.md) treats
each image independently, and parallel fetching preserves that: one worker
raising a timeout must not cancel its siblings. Each task resolves to its own
tier — fresh, stale, or placeholder — and `gallery.py` assembles whatever comes
back.

**The per-image timeout bounds the page.** With `GALLERY_UPSTREAM_TIMEOUT` at
5 s and retries, a page's worst case is roughly the slowest single image plus
queueing, not the sum of all of them. That is the property that makes a page
timeout predictable.

**Cache reads happen inside the workers.** A warm image never enters the pool's
I/O path at all — it returns from `cache.py` immediately, so a warm page costs
almost nothing regardless of concurrency setting.

### Incoming contention is measured and documented, not fixed

**Validate with a test that asserts the warm-cache property, and document the
cold-cache stampede rather than fixing it.**

The validation is a unit test issuing N concurrent gallery requests and
asserting that a warm cache produces zero upstream calls — the property line 141
actually requires. It runs in-process with a counting stub in place of the
provider, so it needs no server, no network, and no timing tolerance.

**Single-flight coalescing is deliberately not implemented.** The stampede is
recorded as a known limitation with its measured cost, and as the first entry
under Future Improvements.

## Consequences

**A cold page is usable.** 454 ms for 10 images and ~1.4–2.5 s for 50, against
3.8 s and ~19 s serially. This is the difference between a working gallery and
one that times out.

**Concurrency multiplies instantaneous upstream load.** Ten workers means up to
ten simultaneous connections per worker process, and with two gunicorn workers
that is twenty. Bounding the pool is what keeps this civil; raising
`GALLERY_FETCH_CONCURRENCY` raises pressure on the provider proportionally.

**It compounds with the stampede below.** Five users loading a cold page
concurrently, each fanning out to ten workers, is fifty in-flight requests where
ten distinct images were needed. Both effects are on cold keys only, and both
disappear once the cache is warm — but they multiply rather than add.

**Threads need care with Django state.** Workers must not touch the request
object or anything request-scoped; they receive plain values and return
`ImageResult` objects ([ADR 13](0013-module-structure.md)). Django's cache is
thread-safe, so `cache.py` is safe to call from inside the pool.

**Ordering must be restored explicitly.** Results arrive out of order; the grid
must render in id order regardless of which fetch finished first.

**The observed behaviour is reportable, which is what line 148 asks for.** The
numbers above go in the README's performance section: warm cache eliminates
upstream traffic entirely; cold cache under concurrency multiplies it by the
number of simultaneous clients.

**The stampede is bounded in practice by three things.** It only occurs on a
cold key — the window is one upstream round trip, 300–515 ms measured. It
requires genuinely simultaneous first-requests for the same image. And with two
gunicorn workers and a per-worker cache ([ADR 11](0011-cache-sizing.md)), some
duplication already exists and was priced as acceptable there.

**The honest cost:** a cold start under load hits picsum harder than necessary.
For a gallery whose images are immutable and whose catalogue is 100 ids, the
worst case is bounded and transient. For a high-traffic deployment it would not
be.

**Why not fix it:** single-flight requires a per-key lock held across an I/O
operation. In a threaded worker that is a `threading.Lock` per key with its own
lifecycle and eviction; across processes it needs shared state, which
[ADR 1](0001-no-database.md) and brief line 17 rule out. The result would be
correct only within one worker while adding lock-management code, a new class of
bug (a lock held across a hung upstream call blocks every waiter until timeout),
and a failure mode to test. Measured against a transient 5× on cold keys, the
trade is not worth it here — but it is exactly the right first improvement if
traffic grows.

**Concurrency tests must not assert on timing.** The test asserts *call counts*,
not elapsed milliseconds, so it cannot flake on a loaded CI machine. The timings
above are reported as measurements, never as assertions.

## Alternatives rejected

**Fetch a page's images serially.** Simplest, and needs no thread pool.
Rejected on the measurements: ~3.8 s for a cold 10-image page and ~19 s for 50.

**An unbounded pool sized to the page.** Fifty workers for a 50-image page is
faster still, but opens fifty simultaneous connections to one host per request,
exhausts local sockets under concurrent load, and is the kind of traffic that
gets a client throttled. Ten recovers most of the benefit.

**`asyncio` with an async HTTP client.** The conventional answer for I/O fan-out
and it scales further than threads. Rejected because the surrounding stack is
synchronous WSGI — adopting it means either an async view stack or bridging with
`async_to_sync`, and adding an async HTTP dependency. The work is ten to fifty
blocking I/O waits, which a bounded thread pool handles without changing the
application's execution model.

**Implement single-flight coalescing.** The correct fix, and the obvious one.
Rejected for the reasons above: it works only per-worker without shared state,
adds a lock held across I/O, and addresses a transient cost on cold keys only.
Recorded as Future Improvement rather than dismissed.

**Probabilistic early expiry.** Refreshing entries slightly before expiry to
avoid synchronised expiry stampedes. Solves a different problem — this
application's stampede is on cold keys, not expiring ones, and immutable content
means expiry is not a correctness event
([ADR 12](0012-resilience-strategy.md)).

**Cache warming at startup.** Prefetching the first page would remove the most
likely cold-stampede case. Rejected because it contradicts
[ADR 4](0004-bounded-catalogue.md)'s central property — nothing is enumerated or
prefetched, and pages are composed on demand — and it would make container
startup depend on upstream availability.

**A load-testing tool (locust, k6).** Would produce richer numbers. Rejected as
the opposite of "lightweight": a new dependency and a running server, to measure
something a threaded unit test measures adequately.

**Skip concurrency validation entirely.** Line 148 requires it explicitly.
