# 22. The detail page is a shell too; a rejected parameter is answered, not redirected

## Context

Choosing a custom size of `3000x1000` on the detail page hung the browser.

The immediate cause was a redirect loop. `_chosen_size` read **two** parameters
— `custom_detail_size` and `detail_size` — because the panel has two size
controls and a browser submits both. `_corrected_url` dropped only
`detail_size`. So the corrected URL still carried `custom_detail_size=3000x1000`,
the next request rejected it again, and the page redirected to itself until the
browser gave up. Twenty-one requests in 200 ms, all identical, sit in the log.

That is a one-line bug with a one-line fix, and fixing it exposed two larger
things.

**The banner was lying.** It said *"3000x1000 isn't a valid size — showing
medium."* while the page showed `large`. One hardcoded sentence served both
views, and their fallbacks differ: the gallery's default is `medium`, the
detail page's is `large` ([ADR 7](0007-detail-view-size.md)). It also never
said *why* — that the ceiling is 1600 — which is the only part the user could
have acted on.

**The wording lived in two places.** `image_gallery/validation.py` and
`static/js/derive.js` each held a copy, because the detail page was
server-rendered and the gallery was not. Only the Python copy could read
configuration, so only it could say "between 16 and 1600" without going stale
when `GALLERY_MAX_DIMENSION` was retuned.

The duplication was a symptom. The application had **two rendering models**:
the gallery derived its grid in the browser
([ADR 2](0002-client-side-rendering.md), [ADR 20](0020-ids-are-derived-in-the-browser.md)),
while the detail page was Django templates. Anything both pages need — a notice,
a size rule, a control — had to be written twice and kept in step by hand.

## Decision

**The detail page becomes a shell, like the gallery.** The server sends markup
and a script; the script fetches `/api/images/<id>` and builds the page from
the payload. One rendering model, not two.

`docs/api-contract.md` had already specified this endpoint under *Planned*,
including the sentence "This is what the detail view's parameters panel renders
(F4.4)". Implementing it is finishing the design, not reversing it.

**The payload reports resolved values, which is why it must exist.** ADR 7
forces the size up — browsing at `small` and opening an image gives `large` —
and the client cannot derive that from the URL it was opened with. The panel
exists to disclose the substitution, so the value it reports has to come from
whoever performed it.

**A rejected parameter is answered in the same response, not redirected.**
The endpoint applies the fallback, reports it in `notices`, and returns `200`;
the client renders the banner and drops the rejected parameter from the address
bar with `replaceState`.

> "Redirect" in the requirement means *the user ends up somewhere valid, and is
> told why*. It never named an HTTP status. A `3xx` is one way to achieve it;
> answering with the correction and letting the client tidy the URL is another,
> and it costs one round trip fewer.

**The sentences are written server-side.** They quote configured bounds, so
they cannot drift from the validator that enforces them. There is one copy of
the detail page's wording, in `validation.py`, and `notice_messages` takes a
`bounds` argument rather than hardcoding numbers.

**The shell still 404s an id outside the catalogue.** The id is in the path, so
it is known before any script runs, and a bookmark, a crawler, and a `curl` all
need to see the refusal at the document. A bad *parameter* is different: it has
a sensible substitute, so it recovers ([ADR 6](0006-recover-and-explain.md)).

## Consequences

**The redirect loop is now structurally impossible.** Nothing redirects, so no
list of parameters can be got wrong in a way that produces one. The regression
test asserts the property that matters — fallback and explanation arrive
together in one response — rather than guarding the specific list that was
missing an entry.

**The banner cannot misreport the fallback**, because it no longer names one.
It says what was refused and what would be accepted; the page already displays
the size it settled on, in the control and in the readout beside it.

**`notices` is back, but not where ADR 19 removed it from.**
[ADR 19](0019-validation-errors-carry-a-usable-payload.md) removed `notices`
from `/api/images` — the *page* endpoint, since deleted — and kept `400` as the
answer for a client that sends a bad parameter. That reasoning holds and is
untouched: `/img/<id>` still refuses with a `400`, because an `<img>` asking for
something impossible is a client bug. `api_image` is the other case, a person
pasting a URL, where recovery is the point.

**One duplication narrows rather than disappears.** `derive.js` keeps
`noticeMessages`, because the gallery still reads `?notice=` tokens from its
own redirect and has no payload to read sentences from. The detail page no
longer uses it. Unifying the last copy means giving the gallery a payload too,
which is a larger change than this one and is not attempted here.

**The e2e scenarios needed no changes**, and one step did. Every `data-testid`
is preserved and the script populates the same elements, which is the point of
binding tests to testids rather than to markup. `detail.feature:205` asserts
`200` for an invalid blur — previously a `200` reached after following a `302`,
now a `200` directly.

The step that changed is `the image is rendered at size "<size>"`. It read the
fake upstream's request log, which was sound while every control change caused
a navigation and therefore a fetch. Now a change re-renders, so **choosing the
size the page already shows produces an identical `src` and the browser reuses
the image it holds** — nothing is fetched, and the log has nothing to say. The
step reads the rendered `src` instead: the same fetch-time decision, observed
where it survives. The alternative was a cache-buster, which would mean doing
pointless work in production to keep a test's chosen instrument working.

**Tests moved with the content.** Nineteen assertions in
`test_detail_view.py` probed rendered HTML for things like `"size=large" in
body`. Those were always proxies for "what size did the server resolve?", and
they now ask the payload directly in `test_api_image.py`. What is left in
`test_detail_view.py` is what the shell alone decides: the 404, the id it
publishes, and the absence of baked-in image data.

**A moment of empty frame** before the fetch resolves, which the gallery
already has. The frame reserves its space, so nothing reflows when the image
lands.

## Alternatives considered

**Fix the parameter list and stop.** One line, and the crash goes away. It
leaves the banner lying about the fallback, the wording duplicated, and the
next person to add a size control free to reintroduce the same loop.

**Keep server rendering; publish the bounds as data attributes.** The banner
could then quote real limits without an endpoint. It keeps two rendering models
and two copies of the wording, and does nothing about the resolved-size
problem, which is the reason the panel is hard to get right.

**Server-render the sentences into the HTML for JS to read.** Fixes the
duplication without an endpoint, but it is a JSON payload smuggled through a
`data-` attribute — all of the coupling, none of the contract.
