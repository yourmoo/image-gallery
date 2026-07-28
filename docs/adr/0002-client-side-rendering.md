# 2. Client-side rendering with a JSON API

**This decision was made, reversed, and reinstated.** The project moved from
client-side rendering to server-side rendering and back. Both directions are
recorded here, because the arguments on each side are real and the round trip is
the honest history.

## Context

The application must render a paginated grid of transformable images. Two
architectures were available: Django templates rendering HTML server-side, or
Django exposing JSON with the browser building the DOM.

The decision changed twice.

**First: client-side rendering**, for the user experience and the architectural
separation described below.

**Then: server-side rendering.** Brief line 48 requires invalid page values to
redirect to page 1 with a message. Under client-side rendering there are two
requests carrying `?page=` — the document request for the shell and the API
request for the data — and an HTTP redirect only covers the first. In-app
pagination makes no document request, so the correction has to be duplicated in
JavaScript. That prompted a re-examination which surfaced three further costs:
an API surface no requirement asks for, the loss of the in-process test tier,
and requirement F5.2 becoming trivially satisfiable.

**Finally: client-side rendering again**, as a deliberate architectural
preference after weighing those costs. This is the current and final decision.

## Decision

Django exposes a JSON API. The browser fetches gallery data and builds the DOM.
Django serves an application shell, the JSON endpoints, and — per
[ADR 3](0003-django-as-image-proxy.md) — the image bytes themselves.

## Why client-side rendering

The advantages, stated plainly, because they are the justification for accepting
the costs in the next section.

**A real API surface, documented as a contract.** The brief requires an API
contract section (line 227). With server-side rendering that section describes
three HTML pages and their query parameters — thin material. With a JSON API it
describes actual endpoints, request and response schemas, status codes, and
error payloads. The API becomes a designed artefact with a versionable contract
rather than an implementation detail of a template.

**Presentation and data are genuinely separated.** The backend answers "what
images, with what parameters"; the frontend answers "how this looks". Neither
can quietly absorb the other's responsibility, which is the separation brief
lines 87–92 ask for, expressed at the transport boundary rather than only
between Python modules.

**Honest loading states.** Brief line 163 requires a loading indicator while
gallery images download. Server-rendered HTML arrives complete, so there is no
JavaScript-observable loading state and the best available answer is per-image
CSS placeholders. Client-side rendering makes the loading state explicit: the
application knows when a fetch is in flight and can show it directly, including
for pagination and filter changes that server rendering would express as a full
page reload.

**Navigation without full page reloads.** Changing a filter or turning a page
replaces the grid rather than re-fetching, re-parsing, and re-rendering an
entire document. Smaller payloads per interaction and no flash of a reloading
page.

**The client is replaceable.** A documented JSON API can serve a different
frontend — a mobile client, another framework — without touching the backend.
That is the same argument [ADR 5](0005-service-layer-boundary.md) makes for the
provider boundary, applied at the other edge.

**A correction worth stating:** client-side rendering does **not** reduce
backend load in this application. Django proxies every image byte
([ADR 3](0003-django-as-image-proxy.md)), so a 10-image page is 10 proxied
requests either way, plus one JSON request that server rendering would not make.
The backend does marginally *more* work. What moves to the client is HTML
assembly, which for a grid of `<img>` tags is microseconds of template
rendering. The genuine efficiency gains are smaller per-navigation payloads and
no repeated document parsing — real, but modest, and not a load argument.

## Consequences

**A JSON API must be designed, validated, documented, and tested.** It is not
described by the brief; it exists because of this decision. It needs its own
parameter validation, error payloads, and status-code behaviour, all consistent
with the HTML surface.

**Behavioural testing moves entirely to the browser.** The Django test client
cannot execute JavaScript, so it would only ever see an empty shell. All 74
Gherkin scenarios run through Playwright against a running container. See
[ADR 15](0015-test-strategy.md) for how the tiers divide and how the coverage
gate is satisfied without them.

**Coverage measures unit tests only.** Browser tests exercise Django inside a
container that the in-process coverage tool cannot see, so `tests/unit/` alone
carries the 70% gate (line 173). This is accepted deliberately: coverage
measures unit-level exercise of the service layer, while Gherkin completeness —
every scenario bound to a step definition — is enforced separately and is the
real measure of behavioural coverage.

**Invalid page handling needs two paths.** The API rejects an invalid page with
a validation error; the client corrects the URL with `history.replaceState` and
shows the notice. Brief line 48's redirect is satisfied on the initial document
request, where a bad URL can be pasted or bookmarked. Both paths share one
validator in the service layer, so the rule is defined once.

**Requirement F5.2 is satisfied trivially.** "Templates must not construct image
URLs" holds because there are almost no templates. The substantive constraint —
that image URLs come from the backend — is enforced by the API returning
finished URLs and the client never composing one.

**The application requires JavaScript.** There is no no-JS fallback. Acceptable
for an image gallery; it would not be for content that must be indexable or
accessible without scripting.

## Alternatives rejected

**Server-side rendering with Django templates.** Simpler in several concrete
ways: no API surface to invent, in-process behavioural tests that count toward
coverage, one code path for the line 48 redirect, and no JavaScript requirement.
This was the decision for part of the project's life and the reasons above are
genuine. Rejected because the API contract, the presentation/data separation,
and the loading and navigation experience were judged more valuable than the
testing and simplicity advantages.

**Server-side rendering with progressive enhancement.** Server-rendered HTML
plus JavaScript intercepting pagination and filter changes. Delivers much of the
navigation and loading benefit while keeping the in-process test tier. Rejected
because it retains no API contract, and the enhancement layer would need the
same data the API provides — arriving at a JSON endpoint by a less direct route.
