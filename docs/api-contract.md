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
| `api_image` | `/api/images/1` | GET | `application/json` |
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

**A shell.** It carries no image data: the script fetches `api_image` and
builds the page from the payload
([ADR 22](adr/0022-the-detail-page-joins-the-client.md)). What it does carry is
the id — known from the path before any script runs — and the reversed API
route, so no path is written in JavaScript (F5.4).

| Attribute | Source | Purpose |
| --- | --- | --- |
| `data-image-id` | The path | Which image to ask about |
| `data-api-url-template` | `reverse("api_image", args=[0])` | Where to ask |

`200` for any id inside the catalogue, **including one with a bad parameter** —
the payload reports the fallback and explains it. An id outside the catalogue
returns `404`: it has no sensible substitute, and a bookmark or a crawler needs
to see that at the document.

The parameters below are read by `api_image`, not by this route, but they are
what a user's URL carries and are listed here because this is the address they
paste.

Accepts the same parameters as `index`, plus `detail_size`, and applies one
rule of its own on arrival: **size is forced up, filters carry over untouched**
([ADR 7](adr/0007-detail-view-size.md)).

| Parameter | Meaning |
| --- | --- |
| `size` | The **gallery's** size. Governs the back link, and sets the arrival default via the rule below. |
| `detail_size` | A size chosen **on this page**. Overrides the default, including downwards. |

Two parameters rather than one, so a choice made here stays here: opening a
single image at `small` must not silently re-render the whole grid on return
([ADR 7](adr/0007-detail-view-size.md) § Amendment).

| Gallery was showing | The detail page renders at |
| --- | --- |
| `small`, `medium`, `large` | `large` |
| `300x300` (below `large`) | `large` |
| `1200x900` (above `large`) | `1200x900` — dropping to `large` would make the detail view *smaller* than the grid |
| `grayscale`, `blur` | unchanged |

The parameters panel reports the **resolved** values, so `size` reads `large`
even when the gallery was showing `small`. That is the point of it: this page
silently changes one of the user's parameters, and the panel is where they find
out (F4.4). It is also the control surface — each value is shown in the widget
that sets it, so report and control cannot disagree.

### `api_image` — one image, described

What the detail shell fetches to fill itself in. It reports **resolved**
values — what will actually be served, which differs from what was requested
whenever ADR 7's rule fires or a parameter falls back — and those cannot be
derived from the URL by the client that sent it.

Takes the same parameters as `detail`.

```json
{"id": 3, "url": "/img/3?size=large", "backUrl": "/?page=2&size=small",
 "size": "large", "grayscale": false, "blur": 0,
 "customSize": "", "namedSizes": ["small", "medium", "large"],
 "maxBlur": 10, "notices": []}
```

| Field | Meaning |
| --- | --- |
| `url` | The bytes, at this application's `image` route. **Complete and used verbatim** — the server builds it by reversing the route (F5.2, F5.4), so no URL-construction rule lives in JavaScript. |
| `backUrl` | The gallery the user came from, with **its** size, not this page's (F4.1). |
| `size` | Resolved. `large` even when the gallery was showing `small`. |
| `customSize` | The `WxH` value for the field, empty when a named size is active — a `<select>` cannot display a value it does not list. |
| `namedSizes`, `maxBlur` | What the controls may offer, from configuration, so a widget cannot offer a value the validator would reject. |
| `notices` | What was rejected, and why. Empty when everything was honoured. |

**An invalid parameter is recovered and explained here**, in the same response:

```json
{"notices": [{"code": "invalid_size", "value": "3000x1000",
  "message": "\"3000x1000\" isn't a size we can show. Pick small, medium, large, or type a custom size between 16 and 1600 pixels."}]}
```

`code` and `value` let a client act on the rejection — highlight the offending
control — without parsing English; `message` is the part a person reads. The
sentence is written server-side so it can quote configured bounds, and so the
wording has one home rather than a copy in JavaScript that goes stale when a
setting is retuned.

No redirect is involved. The requirement is that a user asking for something
unavailable is recovered and told; that never required a `3xx`, and doing it in
one response spares a round trip. The client drops the rejected parameter from
the address bar itself.

**Performs no upstream I/O.** Every field is derived from the request and from
configuration, so it answers at local speed even while upstream is down
([ADR 17](adr/0017-image-fetch-timing.md)). It therefore cannot report that an
image failed to load: that is not known until the bytes are fetched, so failed
tiles are counted by the client.

An id outside the catalogue returns `404`.

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

**There is no page-metadata endpoint.** A page of ids is arithmetic over the
catalogue bound, which the shell already publishes, so the client derives it
rather than fetching it
([ADR 20](adr/0020-ids-are-derived-in-the-browser.md)). Loading a gallery page
is one document request followed by one `image` request per tile; opening a
detail page is one document request plus one `api_image` call.

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
