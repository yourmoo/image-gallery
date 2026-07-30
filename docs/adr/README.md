# Architecture decision records

One file per decision: the context that forced it, what was decided, what it
costs, and which alternatives were rejected and why.

These are **records, not proposals**. Every ADR here documents a decision
already taken and reflected in the code or the specifications. Where a decision
is still open, it is listed under [Open questions](#open-questions) rather than
given a speculative ADR.

| # | Decision | Consequence you should know |
| --- | --- | --- |
| [1](0001-no-database.md) | No database | State is URL-driven and cache-backed; no sessions, so no `django.contrib.messages` |
| [2](0002-client-side-rendering.md) | Client-side rendering with a JSON API | Decided, reversed, and reinstated — the round trip and both arguments are recorded |
| [3](0003-django-as-image-proxy.md) | Django proxies image bytes | The browser never learns picsum.dev exists; caching means bytes, not metadata |
| [4](0004-bounded-catalogue.md) | Bounded catalogue via config | Gives a real last page; instances cannot disagree about the bound |
| [5](0005-service-layer-boundary.md) | Service layer owns the provider | Views and templates never construct an image URL |
| [6](0006-recover-and-explain.md) | Invalid parameters recover | Bad values fall back and explain; recovery mechanism **amended by 19** |
| [7](0007-detail-view-size.md) | Detail view always renders large | Size is presentation; only filters carry over |
| [8](0008-configuration-in-settings.md) | `settings.py` alone reads the environment | Enforced by an AST test, not convention |
| [9](0009-url-vocabularies.md) | Client and upstream URLs are separate vocabularies | Client URLs survive a provider change; `seed` never reaches the browser |
| [10](0010-configurable-and-custom-sizes.md) | Named sizes configurable; custom dimensions bounded | `size` accepts `1200x900`; a ceiling bounds both forms, because the provider enforces nothing |
| [11](0011-cache-sizing.md) | One `LocMemCache`, entry cap derived from a byte budget | Cap drops 1000 → 300; per-worker duplication accepted; the disk tier was measured and rejected |
| [12](0012-resilience-strategy.md) | Per-image failure, three tiers, stale-cache fallback | A page renders what it can; freshness and retention are separate windows |
| [13](0013-module-structure.md) | Six modules; `provider.py` alone knows picsum | Class-based views one per file; the provider returns bytes **and** resolved parameters |
| [14](0014-concurrency-validation.md) | Parallel per-image fetching, bounded at 10 | Fan-out half **amended by 17**; the measurements and the cold-key stampede stand |
| [15](0015-test-strategy.md) | Playwright for behaviour, units for coverage | Coverage measures the service layer; Gherkin binding is the behavioural gate |
| [16](0016-api-contract.md) | Hand-written contract, test-enforced | Drift fails the build; no OpenAPI, no new dependency |
| [17](0017-image-fetch-timing.md) | Images fetched per browser request, not during the metadata call | `/api/images` makes no upstream call; no server-side thread pool; the degraded banner is counted client-side |
| [18](0018-shared-cache-in-shared-memory.md) | Cache in tmpfs, shared by every worker | Replaces the per-process cache of **11**; corrects 11's claim that LocMemCache evicts LRU-style |
| [19](0019-validation-errors-carry-a-usable-payload.md) | A 400 carries errors only; recovery happens at the document boundary | Amends **6**'s re-request; the client cannot send an invalid parameter, so a 400 in the browser is a client bug |
| [20](0020-ids-are-derived-in-the-browser.md) | No page-metadata endpoint; the client derives the id range | Removes the `/api/images` of **17**; page arithmetic now runs on both sides and must agree |
| [21](0021-observability-and-the-exception-boundary.md) | Structured request logging in middleware, which is also the exception boundary | Replaces gunicorn's access log; no traceback reaches a client even with `DEBUG=True` |
| [22](0022-the-detail-page-joins-the-client.md) | The detail page is a shell fed by `api_image`; a rejected parameter is answered, not redirected | One rendering model, one copy of the wording; the redirect loop that prompted it is now impossible |

**Amended:** [12](0012-resilience-strategy.md) — images are now served
`Cache-Control: immutable` for a week and the server TTL raised to an hour, so
a reload costs zero requests rather than fifty cheap ones. Placeholders are
`no-store`.

## Format

Context, Decision, Consequences, Alternatives rejected. No status or supersession
ceremony — when a decision changes, the ADR is rewritten and says so in place, as
[ADR 2](0002-client-side-rendering.md) does.

Detailed requirement reasoning lives in [core-features.md](../core-features.md).
ADRs link to it rather than restating it, so the two cannot drift.

## Open questions

None. Every architectural question raised so far has an ADR above.

**Nothing here is implemented yet.** These records specify an application whose
service layer, views, and templates do not exist — the next step is building
against them, and decisions that do not survive contact with code should be
rewritten here rather than quietly abandoned.

## Known limitations, deliberately accepted

Recorded so they are choices rather than oversights. Each has its reasoning in
the ADR named.

| Limitation | Cost | ADR |
| --- | --- | --- |
| Cache is per-worker | One extra upstream fetch per worker per key | [11](0011-cache-sizing.md) |
| Cold-key stampede under concurrency | Measured 5× duplicate fetches; single-flight deferred | [14](0014-concurrency-validation.md) |
| No fallback on a cold start during an outage | Placeholder tiles; no storage layer can fix this | [12](0012-resilience-strategy.md) |
| Custom dimensions can evict the working set | Degrades latency, never correctness | [10](0010-configurable-and-custom-sizes.md) |
| Nothing survives a restart | Cold cache after deploy; matches brief line 81 | [12](0012-resilience-strategy.md) |
