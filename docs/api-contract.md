# API contract

Every endpoint this application serves, its accepted parameters, and how it
behaves when they are wrong.

> **This document is test-enforced.** `tests/unit/test_api_contract.py` parses
> the Endpoints table below and fails if it does not match the URLconf, so an
> endpoint added, removed, or renamed without updating this file breaks the
> build. Drift is a test failure, not a silent lie.

## Endpoints

| Route name | Path | Method | Response |
| --- | --- | --- | --- |
| `index` | `/` | GET | `text/html` |
| `detail` | `/images/1` | GET | `text/html` |
| `image` | `/img/1` | GET | `image/jpeg` |
| `healthz` | `/healthz` | GET | `application/json` |

Internal links are built by reversing **route names**, never by writing paths
(brief line 80), so the middle column can change without touching a template.

A parameterised route is listed with a **worked example** — `/images/1` rather
than `/images/<id>` — so the table stays literally checkable: the test resolves
each path and asserts it reaches the named route.

### `index` — application shell

Returns the HTML shell. The gallery is rendered in the browser
([ADR 2](adr/0002-client-side-rendering.md)), so this response carries no image
data — but it does carry the bounds the client needs to derive one, published as
data attributes on the grid container:

| Attribute | Source | Purpose |
| --- | --- | --- |
| `data-page` | Validated `?page=` | Which page to render |
| `data-count` | Validated `?count=` | How many tiles it holds |
| `data-catalogue-size` | `GALLERY_CATALOGUE_SIZE` | Where the collection ends |

The client computes the id range from these rather than fetching it
([ADR 20](adr/0020-ids-are-derived-in-the-browser.md)). They are configuration
handed to the client, never values it decides: the server still validates every
parameter here and again at `/img/<id>`.

`200` for a valid request. An invalid parameter is corrected here rather than
passed on — see [Parameter handling](#parameter-handling).

### `detail` — one image, on its own page

A **page**, not bytes — `/img/<id>` serves those. Two routes because a user
links to and bookmarks the first while an `<img>` element fetches the second,
and one path cannot be both.

Accepts the same parameters as `index`, and applies one rule of its own: **size
is forced up, filters carry over untouched**
([ADR 7](adr/0007-detail-view-size.md)).

| Gallery was showing | The detail page renders at |
| --- | --- |
| `small`, `medium`, `large` | `large` |
| `300x300` (below `large`) | `large` |
| `1200x900` (above `large`) | `1200x900` — dropping to `large` would make the detail view *smaller* than the grid |
| `grayscale`, `blur` | unchanged |

The parameters panel reports the **resolved** values, so `size` reads `large`
even when the gallery was showing `small`. That is the point of it: this page
silently changes one of the user's parameters, and the panel is where they find
out (F4.4).

Like `index`, this is a document boundary — an invalid parameter is corrected
by a redirect rather than refused. An id outside the catalogue is the exception
and returns `404`: it has no sensible substitute.

### `healthz` — liveness

```json
{"status": "ok"}
```

Always `200` while the process is serving. **Does not check the upstream image
provider**: the application is live even when upstream is unavailable, because
it degrades to placeholders rather than failing (see
[ADR 12](adr/0012-resilience-strategy.md)). A health check that failed on
upstream trouble would cause an orchestrator to restart a container that is
working correctly.

This route is deliberately independent of the gallery: it reads no query
parameters and calls no service.

## Planned endpoints

Specified but **not yet implemented**. Listed here because the contract is the
thing being designed against, and excluded from the enforcement table above
because they are not yet routed.

| Route name | Path | Response |
| --- | --- | --- |
| `api_image` | `/api/images/<id>` | `application/json` — one image |

**There is no page-metadata endpoint.** A page of ids is arithmetic over the
catalogue bound, which the shell already publishes, so the client derives it
rather than fetching it
([ADR 20](adr/0020-ids-are-derived-in-the-browser.md)). Loading a page is one
document request followed by one `image` request per tile.

### `api_image` — one image

Describes a single image. It survives the removal of the page endpoint because
it reports **resolved** values — what was actually served, which may differ from
what was requested when a parameter fell back — and those cannot be derived from
arithmetic. This is what the detail view's parameters panel renders (F4.4).

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `size` | string | server default | A named size, or `WxH` pixels |
| `grayscale` | boolean | false | Combines with `blur` |
| `blur` | integer 0–10 | 0 | Combines with `grayscale` |

```json
{"id": 1, "url": "/img/1?size=large", "width": 800, "height": 800,
 "grayscale": false, "blur": 0}
```

`url` points at this application's `image` endpoint, never at the upstream
provider, and is **complete**: it already carries whatever variation parameters
are active, so it is used verbatim. The client never appends to it or assembles
one from the sibling fields — the server builds it by reversing the route, which
is what F5.2 and F5.4 require and what keeps a URL-construction rule out of
JavaScript.

**Performs no upstream I/O.** Every field is derived from the request and from
configuration, so it answers at local speed even while upstream is down
([ADR 17](adr/0017-image-fetch-timing.md)). It therefore cannot report that an
image failed to load: that is not known until the bytes are fetched, so failed
tiles are counted by the client and the degraded banner is rendered in the
browser.

An id outside the catalogue returns `404`.

### `image` — image bytes

Serves image bytes proxied from upstream, and is the only endpoint that returns
bytes rather than JSON. Every `<img>` in the grid points here, so the browser
never contacts the provider directly.

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `size` | string | server default | A named size, or `WxH` pixels |
| `grayscale` | boolean | false | Combines with `blur` |
| `blur` | integer 0–10 | 0 | Combines with `grayscale` |

**Always `200` when the id is in range**, whatever happened upstream. Four tiers
answer, in order, and `X-Image-Source` names the one that did:

| `X-Image-Source` | Meaning |
| --- | --- |
| `cache` | Served from the freshness window, no upstream call |
| `upstream` | Fetched now, and cached on the way out |
| `stale` | Past the freshness window but still retained — upstream was unreachable |
| `placeholder` | Nothing cached and upstream unreachable |

The header exists because the bytes alone cannot distinguish a placeholder from
a real image, and the client counts degraded tiles to decide whether to show the
degraded banner ([ADR 17](adr/0017-image-fetch-timing.md)).

An id outside the catalogue returns `404` — it has no sensible substitute,
unlike a bad parameter, which falls back.

## Parameter handling

**Invalid values are rejected.** The API returns `400` with an `errors` array
and no page data:

```json
{
  "errors": [
    {"parameter": "size", "value": "huge", "accepted": ["small", "medium", "large"]}
  ]
}
```

**Recovery happens before the API is called.** A pasted or hand-edited URL is a
document request, so it arrives at `index`, which validates it, applies the
fallbacks, and redirects to the corrected address:

    GET /?size=huge&blur=6  →  302  →  /?size=medium&blur=6&notice=invalid_size

The client then fetches `/api/images` with parameters that are valid by
construction, and renders a notice from `?notice=`. A user who mistypes a URL
gets a working gallery and an explanation; the API never receives the bad value.

**One bad parameter does not discard the good ones.** `?size=enormous&blur=6`
redirects to the default size with blur 6 still applied, and explains only the
size.

Because the client builds every request from its own controls, a `400` reaching
the browser client means the client has a bug rather than that a user erred —
see [ADR 19](adr/0019-validation-errors-carry-a-usable-payload.md).

**Out-of-range dimensions are rejected, never clamped.** Silently serving 1600px
when 6000 was requested would be undetectable to the caller
([ADR 10](adr/0010-configurable-and-custom-sizes.md)).

**Accepted values are not published here.** The `count` allow-list, the pixel
bounds, and the catalogue size are deployment configuration rather than
interface: an operator retuning one changes what the server accepts, not the
shape a client programs against. A rejected value names what is accepted.

`blur`'s 0–10 range is the exception — it is fixed by the contract, not by
configuration.

## Error behaviour

| Case | Endpoint | Status | Body |
| --- | --- | --- | --- |
| Invalid parameter | `index` | 302 → corrected URL | Notice carried in the query string |
| Invalid parameter | `api_image`, `image` | 400 | `errors` only, no image data |
| Invalid page | `index` | 302 → page 1 | Notice carried in the query string |
| Image id outside the catalogue | `api_image`, `image` | 404 | Error payload, no recovery |
| Upstream timeout or failure | `image` | 200 | Stale bytes if cached, else a placeholder |
| No cached fallback available | `image` | 200 | Placeholder; the client marks the page degraded |

**Redirects belong to `index`, not to the API.** A document request can be
pasted or bookmarked, so the address bar is corrected with a 302 carrying
`?notice=`. `/api/images` never redirects: `fetch` follows a 302 transparently,
so the client would never observe it and could not show the notice. Both paths
run the same validator ([ADR 6](adr/0006-recover-and-explain.md)), which is what
keeps a value from being accepted at one entry point and rejected at the other.

An invalid `page` is not a special case — it takes the same route as every other
bad parameter. Brief line 48's "redirect to page 1" is satisfied by the `index`
redirect that already handles `size`, `blur`, `grayscale`, and `count`.

**A `404` does not recover.** Image 101 in a 100-image catalogue has no sensible
substitute, where a bad `size` has one. That asymmetry is deliberate — see
[ADR 6](adr/0006-recover-and-explain.md).

Upstream failures are confined to the `image` endpoint because it is the only
one that calls upstream.

Degraded cases return `200` because the request succeeded — the page rendered.
A `5xx` would claim the application failed when it handled the failure
correctly. See [ADR 12](adr/0012-resilience-strategy.md).

## Vocabulary

Identifiers and named sizes are this API's own. The upstream provider's terms —
its name, and the `seed` parameter it uses for identity — appear nowhere in any
URL, payload, or response, so client URLs survive a provider change
([ADR 9](adr/0009-url-vocabularies.md)).
