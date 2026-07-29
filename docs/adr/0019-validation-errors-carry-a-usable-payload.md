# 19. Validation errors are errors; the client keeps them unreachable

## Context

[ADR 6](0006-recover-and-explain.md) decided that invalid parameters recover
rather than dead-end a user, and split the response by consumer: the JSON API
returns **400** with a machine-readable error, the browser UI renders with the
fallback applied plus a notice. It described the client reconciling the two by
calling the API, receiving the validation error, and **re-requesting with
defaults**.

`docs/api-contract.md` documented the opposite — **200** with the default
already applied and the substitution reported in a `notices` array — and the two
documents sat in contradiction until 2026-07-29.

Both were solving a problem that the architecture had already removed, and
noticing that is what resolved them.

**The client cannot send an invalid parameter.** Under
[ADR 2](0002-client-side-rendering.md) every request to `/api/images` is built
by the client from its own controls: a `<select>` offering exactly
small/medium/large, a checkbox, a 0–10 blur input, a count control offering
exactly the configured allow-list. The values are drawn from the same
allow-lists the server validates against. A `400` reaching the browser client
therefore means **the client has a bug**, not that a user did something wrong.

Designing a recovery payload for that case builds a repair mechanism for a
failure the client is responsible for not causing — and, being unreachable in
normal use, one that would go untested until it was needed.

The genuinely reachable case is a **hand-edited or pasted URL**. That is a
document request, and it never reaches `/api/images` first: it hits `index`,
which already validates and redirects.

## Decision

**A `400` carries the error and nothing else.**

```json
{
  "errors": [
    {"parameter": "size", "value": "huge", "accepted": ["small", "medium", "large"]}
  ]
}
```

No images, no page, no recovered payload. `accepted` names what the parameter
will take, so a caller can correct itself; the allow-list is discoverable at
runtime rather than published in the contract
([ADR 16](0016-api-contract.md)).

**Recovery happens before the API is called, at the document boundary.**
`index` validates the query string on the initial request, applies the
fallbacks, and redirects so the corrected values are in the address bar:

    GET /?size=huge&blur=6  →  302  →  /?size=medium&blur=6&notice=invalid_size

The client then loads with parameters that are valid by construction, fetches
`/api/images` once, and renders the notice from `?notice=`. The user gets a
working gallery and an explanation — what [ADR 6](0006-recover-and-explain.md)
required — and the API never sees the bad value.

Both entry points call the same validator, so the rule is defined once and the
two paths cannot disagree.

| Entry point | Bad parameter arrives from | Response |
| --- | --- | --- |
| `index` | A pasted, bookmarked, or hand-edited URL | 302 to the corrected URL, `?notice=` explaining |
| `/api/images` | A third-party program, or a client bug | 400, `errors`, no payload |

## Consequences

**The API is conventional.** A 4xx means the request failed and the body
explains why. Nothing surprising is asked of a client author, and no
justification for an unusual response shape has to be maintained.

**`notices` is removed from the 200 response shape.** Substitution is now
reported through `?notice=` on the redirect, so a `notices` array on a
successful API response would be permanently empty. Successful responses carry
no notice field.

**A client bug surfaces as a visible failure.** If the client ever does send a
bad parameter, it gets a 400 with no images rather than a silently-corrected
page. That is the desired outcome: the alternative hides the defect behind a
recovery path and the grid renders as though nothing were wrong.

**One extra redirect on a mistyped URL**, which the browser follows without the
application doing anything. Cheaper than the re-request ADR 6 originally
described, because it happens before the client boots rather than after its
first fetch fails.

**The validator runs in two places and must stay one implementation.**
`index` and the API views both call it. This is the coupling to watch: a rule
added to one path and not the other would let a value be accepted at the
document boundary and rejected by the API, which the user would experience as a
gallery that fails to load.

**Invalid page is not special.** Brief line 48 asks for a redirect to page 1 on
an invalid page, and that is exactly what `index` already does for every
parameter — page needed no separate mechanism, it needed the same one.
`/api/images?page=abc` returns 400 like any other bad parameter; it does not
redirect, because `fetch` follows a 302 transparently and the client would never
observe it.

**The degraded banner is unaffected.** Images that fail to load are not known at
metadata time ([ADR 17](0017-image-fetch-timing.md)), so the client counts
failed tiles and renders that banner itself. It looks similar to the validation
notice and is a different mechanism; only parameter substitution travels through
`?notice=`.

## Alternatives rejected

**`400` carrying the recovered page alongside the errors.** Serves both
consumers in one round trip: a program branches on the status, the browser
renders the body. Briefly adopted on 2026-07-29 and rejected the same day —
it builds a recovery path for a request the client cannot make, and an
unconventional response shape (a 4xx containing the resource) is a permanent
cost paid for an unreachable case. Recovering at the document boundary achieves
the same user-visible outcome with a conventional API.

**`200` with a `notices` array** — what the contract previously documented.
Conventional and single-round-trip. Rejected because a program cannot detect
that its parameter was ignored without inspecting a field nothing obliges it to
read, and brief line 65 asks for invalid transformation values to be rejected
with a clear validation error. A `200` is not a rejection.

**`400`, then the client re-requests with defaults** — ADR 6 as originally
written. Rejected because it spends a round trip recomputing what the server
already produced, and because the retry can fail independently of the request
that prompted it. Redirecting at `index` corrects the URL *before* the client
makes any request, so there is nothing to retry.

**Client-side validation only, with the API trusting its input.** The client
already guarantees valid values, so the server check looks redundant. Rejected
outright: `/api/images` is a documented public surface (brief line 227), and an
endpoint that trusts its query string is one hand-edited URL away from passing
an unvalidated dimension to the provider — which
[ADR 10](0010-configurable-and-custom-sizes.md) exists to bound.

**`422 Unprocessable Content` instead of `400`.** Arguably more precise, since
the syntax is well-formed and the value is semantically invalid. Rejected
because 422 is chiefly a WebDAV-derived status whose common use is request-body
validation, and query-parameter rejection is what 400 is for.
