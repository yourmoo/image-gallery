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
| `healthz` | `/healthz` | GET | `application/json` |

Internal links are built by reversing **route names**, never by writing paths
(brief line 80), so the middle column can change without touching a template.

### `index` — application shell

Returns the HTML shell. The gallery is rendered in the browser from the JSON
API, so this response carries no image data.

Always `200` for a valid request.

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
| `api_images` | `/api/images` | `application/json` — a page of images |
| `api_image` | `/api/images/<id>` | `application/json` — one image |
| `image` | `/images/<id>` | `image/jpeg` — the image bytes |

### `api_images` — a page of images

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `page` | integer ≥ 1 | 1 | Out of range redirects to page 1 with a notice |
| `count` | integer | server default | Restricted to a configured allow-list |
| `size` | string | server default | A named size, or `WxH` pixels |
| `grayscale` | boolean | false | Combines with `blur` |
| `blur` | integer 0–10 | 0 | Combines with `grayscale` |

Response shape:

```json
{
  "page": 1,
  "total_pages": 10,
  "count": 10,
  "images": [
    {"id": 1, "url": "/images/1?size=medium", "width": 400, "height": 400,
     "grayscale": false, "blur": 0}
  ],
  "notices": []
}
```

`url` points at this application, never at the upstream provider. `width` and
`height` are what was actually served, which may differ from what was requested
when a parameter fell back.

**This endpoint performs no upstream I/O.** Every field above is derived from
the request and from configuration — ids from page arithmetic, `url` from URL
reversing, dimensions from the resolved `size`. Image bytes are fetched by the
`image` endpoint when the browser requests each tile, so `/api/images` responds
at local speed even while upstream is down
([ADR 17](adr/0017-image-fetch-timing.md)).

Consequently `notices` reports **parameter substitutions only**. Images that
fail to load are not known at this point and are counted by the client as tiles
fail; the degraded banner is rendered in the browser.

### `api_image` — one image

Same parameters as above minus `page` and `count`. Returns a single `image`
object. An id outside the catalogue returns `404`.

### `image` — image bytes

Serves `image/jpeg` proxied from upstream. Accepts `size`, `grayscale`, and
`blur`. This is the only endpoint that returns bytes rather than JSON.

## Parameter handling

**Invalid values do not fail the request.** The default is applied, the page
still renders, and the substitution is reported in `notices` so the client can
explain it. A mistyped URL yields a usable gallery rather than a dead end —
[ADR 6](adr/0006-recover-and-explain.md).

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
| Invalid parameter | any | 200 | Default applied, reported in `notices` |
| Invalid page | `api_images` | 302 → page 1 | Notice carried in the query string |
| Image id outside the catalogue | `api_image`, `image` | 404 | Error payload |
| Upstream timeout or failure | `image` | 200 | Stale bytes if cached, else a placeholder |
| No cached fallback available | `image` | 200 | Placeholder; the client marks the page degraded |

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
