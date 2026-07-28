# 4. The catalogue is bounded by configuration

## Context

Brief line 25 states that picsum.dev provides no list endpoint. Nothing tells
the application how many images exist.

That leaves pagination underspecified. Without a known bound there is no last
page, `?page=999` is as valid as `?page=2`, and "out of range" cannot be
defined, specified, or tested. It also nearly voids line 48's redirect
requirement, which would then only ever fire on non-numeric input.

## Decision

`GALLERY_CATALOGUE_SIZE`, default 100. The application presents images with ids
1 through that bound.

**The catalogue is not a structure that gets built.** It is a single integer in
settings — no enumeration, no boot-time or first-request population step, no
list, no allocation. Image ids are derivable, so the URL for id 47 is
constructed on demand, and only the ids on the requested page are ever fetched.

Each id maps to an upstream seed at request time, per
[ADR 9](0009-url-vocabularies.md). The catalogue is therefore a *range*, not a
collection: bounding it is choosing where the range stops.

## Consequences

**Pagination becomes fully specifiable.** A real last page, a defined
out-of-range case, and next/previous links that disappear at the ends — all
deterministic and testable.

**This is what makes requirement F2.7 true.** A page *is* several upstream
calls, issued when that page is requested. Because nothing is prefetched, page 1
costs 10 upstream calls and ids 11–100 are never touched until someone asks for
them.

**Instances cannot disagree.** Every container reads the same environment
variable, so there is no shared state to drift and no coordination needed. This
is the strongest argument for a configured bound: instances that *discovered*
the boundary by probing could genuinely disagree — different cache states, a
transient 404 on one instance — and two containers behind one load balancer
would report different total page counts for the same collection.

**Growing the catalogue is an operator change plus a restart.** That is the
shape brief line 96 asks for, and it means the bound is a deployment decision
rather than a code change.

**End users cannot browse past the bound**, by design. That is not a limitation
to work around; the bound is what creates the last page and the out-of-range
case in the first place.

**Catalogue size is deliberately not user-adjustable.** Only the per-page count
is exposed as a UI control (requirement F2.5). Exposing catalogue size to the
browser would hand a client an unbounded multiplier on upstream fetches — a
denial-of-service vector against picsum.dev via query string.

## Alternatives rejected

**Unbounded collection.** Every page number valid, only non-numeric or `page<1`
invalid. Simpler, but there is no last page, "out of range" cannot be tested,
and line 48's redirect rule becomes nearly vacuous.

**Discover the bound by probing upstream.** Page forward until picsum returns
404, then treat that as the end. Truest to the provider, but it makes the
boundary depend on a live upstream, costs an extra upstream call at every
boundary check, and — decisively — lets instances disagree about the size of the
collection.

**Hardcode 100.** Same behaviour, but brief line 96 explicitly asks for key
parameters to be environment-driven, and a hardcoded bound cannot be tuned per
deployment.
