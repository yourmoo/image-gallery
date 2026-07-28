# 11. One in-memory cache, bounded by a derived entry cap

## Context

[ADR 3](0003-django-as-image-proxy.md) established that Django caches image
**bytes**, not metadata. That invalidated the original cache sizing, which had
assumed ~1.4 KB payloads, and left three claimed problems with the existing
`LocMemCache` configuration:

1. `MAX_ENTRIES` counts entries rather than bytes, so there is no byte ceiling.
2. Per-process caching means a worker-local miss costs a real upstream fetch,
   roughly doubling upstream traffic across two gunicorn workers.
3. `LocMemCache` pickles values, so round-tripping JPEG byte strings through
   pickle is overhead.

The leading proposal was a two-tier cache: metadata in memory, image bytes on
disk with a byte-capped LRU, shared across workers. Before adopting it, the
three problems were measured.

## Measurements

Taken on 2026-07-28 against picsum.dev and CPython 3.13.

**Byte sizes vary 2–3× with image content**, not only with dimensions. Across
eight seeds per dimension:

| Dimension | min | median | max | mean |
| --- | --- | --- | --- | --- |
| 200×200 | 6.1 KB | 7.8 KB | 14.7 KB | 9.0 KB |
| 400×400 | 15.5 KB | 20.8 KB | 41.0 KB | 24.2 KB |
| 800×800 | 43.3 KB | 59.4 KB | 114.5 KB | 67.8 KB |
| 1600×1600 | 122 KB | 182 KB | 332 KB | 205 KB |

Earlier figures quoted in [ADR 3](0003-django-as-image-proxy.md) were single
samples that happened to land near the minimum of each range.

**Pickle overhead is negligible, contradicting problem 3:**

| Payload | Pickle overhead | Round trip |
| --- | --- | --- |
| 6.6 KB | 18 bytes | 0.006 ms |
| 44 KB | 18 bytes | 0.018 ms |
| 130 KB | 9 bytes | 0.034 ms |

For an opaque byte string, pickle is a length prefix — it does not serialise
structure. **An upstream fetch costs 300–515 ms**, four orders of magnitude
more. Problem 3 is not real.

**Entry cap needed for a given per-worker byte budget**, at the pathological end
of the distribution:

| Budget | Mean-large entries | At-ceiling entries |
| --- | --- | --- |
| 64 MB | 944 | 312 |
| 128 MB | 1888 | 624 |

## Decision

**One `LocMemCache`, with `GALLERY_CACHE_MAX_ENTRIES` reduced from 1000 to
300.** No disk tier, no second cache backend.

`MAX_ENTRIES` is treated as a byte budget in disguise: the cap is *derived* from
a target footprint divided by the worst-case entry size, and is documented as
such so that changing it is a deliberate memory decision rather than a guess.

Resulting per-worker footprint:

| Usage | Footprint |
| --- | --- |
| Typical medium browsing | ~7 MB |
| Large-heavy | ~20 MB |
| Pathological, all at ceiling | ~60 MB |

Doubled across two gunicorn workers.

## Consequences

**The only real problem is fixed by configuration, not architecture.** Of the
three, problem 3 was false, problem 1 is solved by setting the cap correctly,
and problem 2 is accepted below.

**Per-worker duplication is accepted and documented.** A worker-local miss costs
one upstream fetch of 300–515 ms. With two workers the worst case is two fetches
per distinct key rather than one. This is a genuine cost, chosen over a disk
tier whose machinery — LRU implementation, eviction, concurrent access, cleanup,
and a new failure mode — is disproportionate to it. `LocMemCache` already
performs LRU-style eviction via `MAX_ENTRIES` and `CULL_FREQUENCY`.

**The cache holds a working set, not the key space.** The full named-size space
is 100 ids × 3 sizes × 2 grayscale × 11 blur = 6,600 entries, roughly 222 MB per
worker at mean sizes — well beyond the cap. Custom dimensions
([ADR 10](0010-configurable-and-custom-sizes.md)) make the space unbounded in
principle. The cache is therefore explicitly a **hot-set cache**: it makes
repeated and paginated browsing fast, and it never attempts to hold everything.

**Cache eviction by a hostile client remains possible.** Walking custom
dimensions evicts the working set, as noted in ADR 10. A 300-entry cap makes
eviction cheaper to trigger than a 1000-entry one — the accepted mitigation is
that eviction degrades latency, never correctness.

**Nothing persists across restarts.** Brief line 81 scopes caching to "while the
app is running", so a container-local in-memory cache matches the requirement
exactly. No volume, no mount, no staleness question across restarts.

**Cache keys must include every output-affecting input** (brief line 137): id,
resolved dimensions, grayscale, and blur. Because named sizes resolve to
configured pixel dimensions, the key uses the **resolved dimensions** rather
than the name — otherwise changing `GALLERY_SIZE_LARGE` would silently serve
stale bytes under the same key.

## Alternatives rejected

**Two-tier: metadata in memory, bytes on disk with a byte-capped LRU.** The
leading proposal before measurement. It genuinely fixes per-worker duplication
and gives a true byte ceiling. Rejected because its headline justification —
pickle overhead — proved false, and its remaining benefit is avoiding one
300–515 ms fetch per worker per key, at the cost of an LRU implementation,
eviction logic, concurrent-access handling, disk cleanup, and a failure mode
that must be tested. Disproportionate machinery for the problem that remains.

**Keep `MAX_ENTRIES=1000`.** Bounds a worker at ~68 MB of large images and
~205 MB at the ceiling — the latter being an unacceptable container footprint,
doubled across workers.

**A byte-counting cache backend.** A custom backend tracking cumulative bytes
would bound memory precisely rather than by derivation. Rejected as
reimplementing `LocMemCache` for precision the derived cap already approximates
adequately.

**Redis or Memcached.** Would fix per-worker duplication directly and is the
conventional answer. Ruled out by brief line 17, which forbids new external
services. Worth stating plainly: this constraint is what makes per-worker
duplication unavoidable rather than merely tolerated.

## Future improvements

If the deployment scales past two workers, or upstream becomes rate-limited, the
two-tier disk design becomes worth revisiting — the measurements above are the
input to that decision, and the threshold is when duplicated upstream fetches
cost more than the disk tier's complexity.
