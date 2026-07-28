# 12. Per-image resilience with an explicit stale-cache tier

## Context

Brief lines 105–128 require timeout handling, retry with backoff, fallback to
cached data when upstream fails, and an error-handling matrix covering upstream
timeouts, non-success responses, missing data, and the case where no cached
fallback exists. Each case needs clear user-facing behaviour, predictable HTTP
status, and useful logs.

Two properties of this application shape the answer.

**A page is many upstream calls.** [ADR 4](0004-bounded-catalogue.md) means a
10-image page issues 10 independent upstream requests, and a 50-image page
issues 50 — each one triggered by its own `/images/{id}` request from the
browser ([ADR 17](0017-image-fetch-timing.md)). Failure is therefore not binary:
the realistic case is that three images fail while seven succeed.

**The images are immutable.** Verified against picsum.dev: `seed=7` at a given
size returns byte-identical bytes on every request. A cached image cannot become
*wrong* with age — only the memory it occupies is a cost.

The settings already exist (`GALLERY_UPSTREAM_TIMEOUT`,
`GALLERY_UPSTREAM_RETRIES`, `GALLERY_UPSTREAM_BACKOFF`) but nothing consumes
them.

## Decision

### Failure is handled per image, not per page

A page renders whatever it can. Images that fail every tier render as a
placeholder tile, visually distinct from a tile that is still loading. The page
returns **200** with a banner noting that some images are unavailable.

Per [ADR 17](0017-image-fetch-timing.md) each image is its own request, so this
isolation is structural rather than something the page-assembly code has to
preserve: a tile fails on its own because it *is* its own request. The banner is
counted client-side once the grid knows which tiles failed — the metadata
response was sent before any fetch was attempted, so it cannot report them.

Failing an entire page because one of fifty images timed out would be a worse
outcome than a partial gallery — and with fifty independent upstream calls,
all-or-nothing means one slow image can deny the whole page.

### Three tiers per image

| Tier | Condition | Behaviour |
| --- | --- | --- |
| 1 | Fresh cache entry | Serve it. No upstream call. |
| 2 | Upstream failed, stale entry exists | Serve the stale bytes; log the fallback. |
| 3 | Upstream failed, nothing cached | Placeholder tile; mark the page degraded. |

### Freshness and retention are separate windows

Django's cache API has no "return this even though it expired": once the TTL
passes, the entry is gone. Serving stale data therefore requires decoupling
*freshness* from *retention*:

    cache.set(key, (payload, fetched_at), timeout=GALLERY_CACHE_RETENTION)

    entry = cache.get(key)
    fresh  = entry and age(entry) < GALLERY_CACHE_TTL

`GALLERY_CACHE_TTL` (default 300s) governs when the application will *prefer* a
new fetch. `GALLERY_CACHE_RETENTION` (default 3600s) governs how long bytes stay
available as a fallback. TTL becomes a value compared against, not a timer the
cache enforces.

**A stale entry is served only when upstream has actually failed.** It is never
used on the happy path — a stale hit within the retention window still triggers
a fetch attempt first.

### Retry and timeout

Each upstream call uses `GALLERY_UPSTREAM_TIMEOUT` (5s) and retries
`GALLERY_UPSTREAM_RETRIES` (2) times with exponential backoff seeded by
`GALLERY_UPSTREAM_BACKOFF` (0.2s). Retries apply to timeouts and 5xx responses.
A 4xx is not retried — it will not succeed on a second attempt.

### Error-handling matrix

| Case | HTTP | User sees | Logged |
| --- | --- | --- | --- |
| Invalid parameter | 200 | Fallback to default + notice | Validation failure, param and value |
| Upstream timeout | 200 | Stale image, or placeholder | Timeout, attempts, elapsed, tier used |
| Upstream 5xx | 200 | Stale image, or placeholder | Status, attempts, tier used |
| Upstream 4xx | 200 | Placeholder | Status; not retried |
| No cached fallback | 200 | Placeholder + degraded banner | Cold-miss during outage |
| Image id out of range | 404 | Not-found page | Requested id and bound |

The page returns 200 in every degraded case because the page itself rendered
successfully — the brief asks for "clear user-facing behavior, not raw exception
output" (line 126). A 5xx would be claiming the application failed when it
handled the failure correctly.

## Consequences

**Line 111 is satisfied by a distinct, demonstrable code path.** Tier 2 is an
explicit branch that can be tested, logged, and pointed at — "served stale
entry, age 340s" is a log line a reviewer can find. This is the reason two
windows were chosen over the simpler alternative below.

**Immutable content makes stale data free of correctness risk.** Serving an
hour-old image is not a degraded answer; it is the same bytes a fresh fetch
would return. This is unusual — the normal stale-cache trade-off weighs
freshness against availability, and here there is nothing to weigh.

**Every value carries a timestamp**, so cache entries become tuples rather than
raw bytes and every read compares an age. Small, but it is real added mechanism.

**Two settings must stay ordered.** `GALLERY_CACHE_RETENTION` must exceed
`GALLERY_CACHE_TTL` or the stale tier can never fire — retention shorter than
freshness means an entry expires before it can become stale. Enforced by a test.

**Retention interacts with the entry cap.** Longer retention means more entries
resident, so [ADR 11](0011-cache-sizing.md)'s 300-entry cap does the bounding.
Raising retention does not raise the memory ceiling; it raises the chance an
entry is evicted by pressure before expiry.

**The cold-start case is not solved, and cannot be.** Upstream down with nothing
cached yields a placeholder. No storage layer changes this: a cache can only
return what was successfully fetched at some point. This is the honest limit of
"fallback using cached data".

**Degraded rendering needs its own visual language.** A tile that failed and a
tile still loading must not look alike — the design system carries `--warn`
tokens and a "failure never looks like loading" principle for exactly this.

## Alternatives rejected

**Fail the whole page if any image fails.** Simpler and arguably more honest.
Rejected because a 50-image page has 50 chances to fail, so one slow image would
deny the entire gallery.

**Fresh-only cache, no stale tier.** No timestamps, no second window. Rejected
because with a 300-second TTL the failure window rarely overlaps a fresh entry,
so line 111's fallback would almost never actually fire.

**Long TTL with eviction by memory pressure only.** Since the content is
immutable, a one-hour TTL is correct rather than a compromise, and any cache hit
would then serve as an automatic fallback — no timestamps, no age comparison, no
second setting. This was the leading alternative and is a genuinely simpler
design. Rejected because the fallback becomes *emergent* rather than explicit:
there is no branch to test, no distinct log line, and nothing to point at when
justifying the resilience strategy (line 235). The added mechanism buys
legibility.

**SQLite to persist the cache.** Considered and rejected. It would make the
cache survive restarts and be shared across workers, but **it cannot manufacture
data that was never fetched**, so it does not address the cold-start case that
is the actual hard problem. It would also reverse [ADR 1](0001-no-database.md)
for data that is not user-owned, exceed line 81's "while the app is running"
scope, and add write-lock contention on every cache miss — two workers writing
60 KB blobs would serialise on SQLite's database-level write lock. The problem
it genuinely solves, per-worker fetch duplication, was already measured and
priced as acceptable in [ADR 11](0011-cache-sizing.md).

**Redis for a shared cache.** The correct tool for cross-worker sharing, and
ruled out by brief line 17.
