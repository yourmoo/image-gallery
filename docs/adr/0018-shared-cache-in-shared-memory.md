# 18. The image cache lives in shared memory, not in process memory

## Context

[ADR 11](0011-cache-sizing.md) chose a single `LocMemCache` and accepted its
central cost: the cache is per-process, so two gunicorn workers hold two copies
and a hit depends on which worker serves the request.

Writing the BDD suite made that cost concrete rather than theoretical.
`gallery.feature` specifies:

    Scenario: Repeating a request does not call upstream again
      Given I have already opened the gallery
      When I open the gallery again
      Then no further upstream image requests are made

Under `--workers 2`, a repeat page view distributes its ten image requests
across both workers. Whichever land on the worker that did not cache them are
refetched, so the scenario fails — not from a defect, but because the
specification and the process model disagree. Worse, it fails *intermittently*,
which reads as flakiness rather than as a design problem.

## Options considered

**Redis or Memcached.** Ruled out by brief line 17, which forbids new external
services. [ADR 1](0001-no-database.md) already recorded this.

**`DatabaseCache`.** Requires `DATABASES`, contradicting [ADR 1](0001-no-database.md),
plus a `createcachetable` migration step that costs the start-with-one-command
property (brief lines 199–200). Its `value` column is `text`, so image bytes are
base64-encoded — roughly 33% inflation on top of pickle. A poor fit for 20–60 KB
blobs, and SQLite's single-writer lock would serialise exactly the writes that
happen during a slow cold page.

**One worker, many threads.** `--workers 1 --threads 16` makes `LocMemCache`
process-global and keeps the same 16 request slots, since the work is blocking
I/O and the GIL is idle during a fetch. Measured: 16 concurrent upstream fetches
completed in 1.6 s rather than the 8.4 s they would take serialised. Rejected
because it removes worker-level crash isolation, and because it forecloses a
future in which any part of the work becomes CPU-bound.

**A cache directory on tmpfs.** Chosen. See below.

## Measurements

Taken 2026-07-29 inside the runtime container, against payload sizes from
[ADR 11](0011-cache-sizing.md) (medium ~20.8 KB, large ~59.4 KB).

**Latency, single-threaded:**

| Backend | Payload | Write | Read | p95 read |
| --- | --- | --- | --- | --- |
| LocMem | medium | 0.122 ms | 0.024 ms | 0.053 ms |
| FileBased (tmpfs) | medium | 2.574 ms | 0.171 ms | 0.457 ms |
| LocMem | large | 0.244 ms | 0.035 ms | 0.071 ms |
| FileBased (tmpfs) | large | 4.051 ms | 0.128 ms | 0.254 ms |

**Latency under concurrency** — this is the real cost:

| Backend | 1 thread | 4 threads | 16 threads | ops/s @16 |
| --- | --- | --- | --- | --- |
| LocMem | 0.017 ms | 0.018 ms | 0.019 ms | 24,921 |
| FileBased (tmpfs) | 0.149 ms | 2.596 ms | 11.675 ms | 1,216 |

`FileBasedCache` does not scale with threads: file I/O plus zlib decompression
serialise under the GIL, so median latency degrades 78× from 1 to 16 threads
while throughput falls.

**Footprint:** 58.1 KB stored per 59.4 KB payload — about 2% overhead, with no
base64-style inflation.

## Decision

`FileBasedCache` with `LOCATION` on a **tmpfs mount** (`/dev/shm/gallery-cache`,
128 MB), configured by `GALLERY_CACHE_DIR`.

The files never touch a disk. tmpfs is memory, so this is shared memory reached
through the filesystem API — which is precisely what lets separate worker
processes share it. Verified: one process wrote a key, a second process with a
different pid read it back.

`--worker-class gthread --workers 2 --threads 8` is unchanged.

## Consequences

**A cache hit no longer depends on which worker serves the request.** The
scenario above becomes deterministic, and the same 300-entry budget now holds
300 *distinct* images rather than up to 300 duplicated across two workers —
double the effective capacity for the same memory.

**Reads are slower, and the trade is still strongly favourable.** At its worst
measured point — 11.7 ms at 16 threads — a cache hit remains 26–44× cheaper than
the 300–515 ms upstream fetch it replaces. The comparison that matters is
cache-hit versus cache-miss, not cache-hit versus a cache that cannot be shared.

**Throughput has a ceiling of roughly 1,200 cache reads/second per container.**
Well above what a browser capped at 6 connections per origin can demand, but it
is a real ceiling and should be revisited if the deployment grows.

**tmpfs counts against the container's memory limit.** 128 MB of mount plus the
worker heaps must fit. The mount is sized from the 300-entry cap at the
pathological ~182 KB/entry case (~55 MB), leaving headroom.

**Nothing survives a restart**, which matches brief line 81's "while the app is
running" exactly. No volume to manage, no staleness question across restarts.

**The e2e suite gets a cheaper cold-cache fixture.** Emptying a directory
replaces restarting the container.

**Developers outside Docker get a plain directory.** `GALLERY_CACHE_DIR`
defaults to a path beside the project, so behaviour is identical and only speed
differs.

## Correction to ADR 11

[ADR 11](0011-cache-sizing.md) states that "`LocMemCache` already performs
LRU-style eviction via `MAX_ENTRIES` and `CULL_FREQUENCY`". **That is measurably
false.** Writing 350 cold keys into a 300-entry cache holding 50 keys that had
each been read four times:

| Backend | Hot keys surviving |
| --- | --- |
| LocMem | 0 / 50 |
| FileBased | 33 / 50 |

Both cull by random sampling; neither is LRU, and `LocMemCache` evicted the
entire hot set despite recent reads. This weakens ADR 11's reasoning for the
300-entry cap, and it means cache eviction by a client walking custom dimensions
([ADR 10](0010-configurable-and-custom-sizes.md)) is more aggressive than that
ADR assumed. The mitigation is unchanged — eviction degrades latency, never
correctness — but the claim of LRU behaviour should not be relied on.
