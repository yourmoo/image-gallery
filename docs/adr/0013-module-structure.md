# 13. Module structure inside the service boundary

## Context

[ADR 5](0005-service-layer-boundary.md) fixed the *outer* boundary: one
component owns every interaction with the provider, and views never construct an
upstream URL. It deliberately left the internal structure open.

Brief line 92 asks for "a clear module structure (for example: service,
transformations, validation, views)". That is an example, not a mandate — and
taken literally it produces a `transformations` module that, given the decisions
since made, would hold a data class and no behaviour:
[ADR 3](0003-django-as-image-proxy.md) settled that transformations pass through
to the provider rather than being applied locally, so nothing in this
application transforms an image.

The structure below is derived from the seams the decisions actually created,
rather than from the brief's illustrative list.

## Decision

Six modules inside `image_gallery/`, each with one reason to change.

| Module | Owns | Knows about picsum? |
| --- | --- | --- |
| `validation.py` | Allow-lists, the `WxH` grammar, dimension bounds | No |
| `provider.py` | id→seed, named size→pixels, upstream URL, HTTP with retry | **Yes — only this one** |
| `cache.py` | Key construction, the freshness/retention windows | No |
| `gallery.py` | Page composition, per-image fallback tiering, degraded state | No |
| `views/` | Query parsing, rendering, redirects, status codes | No |
| `settings.py` | Every environment read | No |

**Dependency direction is one-way:**

    views → gallery → { provider, cache } → validation
                                          ↘ settings

`validation.py` imports nothing from the others. `provider.py` is the only
module that may name picsum, construct an upstream URL, or import an HTTP
client. Nothing imports from `views/`.

### The provider returns bytes and resolved parameters together

`provider.py` does not return raw bytes. It returns a small result object
carrying the image **and the values actually used to produce it**:

    ImageResult(
        content=b"...",          # the JPEG bytes
        content_type="image/jpeg",
        image_id=7,              # client vocabulary
        width=800, height=800,   # resolved from the named size
        grayscale=True,
        blur=5,
        seed="7",                # provider vocabulary — logs only
        source="upstream",       # upstream | cache | stale | placeholder
    )

These are not fields fetched from picsum — picsum returns image bytes and
nothing else, verified against both the live API and its documentation. They are
values the provider *resolved* while building the request, and it is the only
component that knows both what was asked for and what that became.

This is what requirement F4.4 needs. It also makes two earlier decisions honest
rather than silent: [ADR 7](0007-detail-view-size.md) renders the detail view at
`large` even when the gallery showed `small`, and
[ADR 6](0006-recover-and-explain.md) falls back to a default when a parameter is
invalid. In both cases the user is shown something they did not ask for, and the
parameters panel reporting **resolved** values is what keeps that from being a
substitution they cannot detect.

**`seed` is carried but never rendered.** It is provider vocabulary
([ADR 9](0009-url-vocabularies.md)), so it belongs in logs and diagnostics, not
in the page. The parameters panel shows "Image 7", never "seed 7". Templates
receive a view model without it.

`source` records which tier answered ([ADR 12](0012-resilience-strategy.md)), so
`gallery.py` can count degraded tiles and logs can distinguish a fresh fetch
from a stale fallback without inferring it.

### What each boundary is for

**`validation.py` is the client-vocabulary edge.** It takes raw query values and
returns validated ones plus a list of what was rejected — the input to the
notice banner ([ADR 6](0006-recover-and-explain.md)). It owns the `size`
grammar, which accepts three names or `WxH` within the configured bounds
([ADR 10](0010-configurable-and-custom-sizes.md)). It never resolves a name to
pixels; that is provider vocabulary.

**`provider.py` is the swappable component.** Replacing picsum.dev means
rewriting this module and its tests, and nothing else. It performs both
translations from [ADR 9](0009-url-vocabularies.md) — id to seed, named size to
pixel dimensions — and owns timeout, retry, and backoff
([ADR 12](0012-resilience-strategy.md)).

**`cache.py` keeps the two-window logic in one place.** Because
`GALLERY_CACHE_TTL` is compared in code rather than enforced by the backend,
that comparison must not be scattered. It exposes something closer to
`get_fresh()` / `get_stale()` than a raw `get()`, so the tiering in `gallery.py`
reads as intent. Keys are built from **resolved** values — pixel dimensions, not
size names — so retuning `GALLERY_SIZE_LARGE` cannot serve stale bytes under an
unchanged key ([ADR 11](0011-cache-sizing.md)).

**`gallery.py` is the orchestrator**, and the only module that knows a page is
composed of many images. It walks the id range for a page, applies the three
tiers per image, and reports how many degraded. This is where
[ADR 12](0012-resilience-strategy.md)'s per-image failure policy lives.

**`views/` holds HTTP concerns only** — parsing the query string, choosing
between a redirect and a render, and picking status codes.

### Views are classes, one per file

`views.py` becomes a package, with a single view class per module:

    views/
      __init__.py     re-exports the classes for urls.py
      mixins.py       shared query parsing and validation
      shell.py        AppShellView     serves the HTML shell
      api_gallery.py  GalleryAPIView   JSON: a page of images
      api_detail.py   ImageAPIView     JSON: one image
      image.py        ImageProxyView   serves image bytes
      health.py       HealthView       liveness

Under [ADR 2](0002-client-side-rendering.md) the browser builds the DOM, so most
of these return JSON rather than HTML. `AppShellView` serves the single template
the application has.

Class-based views suit the API views because they share a substantial prologue:
both parse the same query parameters, run the same validation, and report
rejected values the same way. As functions that is a repeated preamble; as
classes it is one mixin, and the difference between them shrinks to what they
return.

`ImageProxyView` returns bytes rather than JSON, and is the only view that
streams a response. Its own module makes that difference visible.

`HealthView` stays deliberately trivial and shares nothing: it must keep working
when the gallery does not, so it depends on no mixin and reads no query
parameters.

**The API views and `ImageProxyView` are the documented API contract**
(brief line 227). They are the surface a client programs against, so their
parameter handling and error payloads are a designed interface rather than an
implementation detail.

## Consequences

**Provider replacement is one module.** The claim in brief line 91 becomes
checkable: grep for `picsum` and every hit should be in `provider.py`, its
tests, or documentation. That is a lint-able invariant, not an aspiration.

**Most logic is testable without Django or network.** `validation.py` and
`provider.py`'s URL construction are pure functions. Only `views.py` and parts
of `gallery.py` need the test client, which is what keeps the fast tier fast and
the coverage gate reachable.

**Requirement F5.3 has an address.** "Centralise URL generation in a
service-layer component" points at `provider.py`, and F5.1–F5.4's unit tests
have an obvious target.

**There is no `transformations.py`,** and that is a deliberate departure from
the brief's example list. Grayscale and blur are validated parameters that pass
through to the provider; with pass-through settled in ADR 3, a transformations
module would hold a data structure and no behaviour. Its two real
responsibilities are already placed: validating the values (`validation.py`) and
expressing them in provider vocabulary (`provider.py`). Adding an empty seam
between them would be structure for its own sake.

**`gallery.py` and `provider.py` must not merge.** The temptation is real, since
both deal with images. The distinction: `provider.py` handles *one* image and
knows the provider; `gallery.py` handles *many* and knows nothing about where
they come from. Merging them would put pagination logic behind the provider
boundary and make the provider unswappable.

**Six modules for an application this size is close to the upper bound.**
Further splitting — separate `keys.py`, `tiers.py` — would be ceremony. If a
module later has no reason to change independently of its neighbour, merge it.

## Alternatives rejected

**Follow brief line 92 literally** — `service`, `transformations`, `validation`,
`views`. Rejected because `transformations` has no behaviour to hold under
pass-through, and because `service` as a single module conflates three distinct
reasons to change: the provider protocol, the caching policy, and page
composition.

**A Django app package** (`gallery/` with `apps.py`, `models.py`). Conventional,
but `models.py` would be empty under [ADR 1](0001-no-database.md), and the app
registry buys nothing when there is one app and no models, admin, or
migrations.

**A single `services.py`.** Fewer files, and defensible at this size. Rejected
because the provider boundary is the thing the brief grades most directly
(lines 89–91), and a module containing pagination, caching, and HTTP does not
demonstrate it.

**Splitting `provider.py` into transport and URL-building.** Cleaner in
principle — pure URL construction separated from I/O. Rejected as premature at
one provider; the URL builder is already a pure function that can be tested
directly without a module boundary around it.

**Function-based views in a single `views.py`.** Simpler, and what the baseline
started with. Rejected because the API views share a substantial
parameter-parsing and validation prologue that would be duplicated or factored
into helpers the functions must each remember to call — a mixin makes it
structural. One class per file also keeps each view small enough to read whole.

**Django REST Framework for the JSON API.** The conventional choice, and it
would supply serialisers, browsable docs, and schema generation. Rejected as
disproportionate: the API has three read-only endpoints, no authentication, no
models, and no writes. `JsonResponse` plus the existing `validation.py` covers
it, and DRF would add a substantial dependency whose main features this
application does not use.

**Returning raw bytes from `provider.py`.** Simpler signature. Rejected because
callers would then re-derive the resolved dimensions and effective parameters to
satisfy F4.4, duplicating logic that only the provider can perform correctly and
allowing the displayed parameters to drift from what was actually fetched.
