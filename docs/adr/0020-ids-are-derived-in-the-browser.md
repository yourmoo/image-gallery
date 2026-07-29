# 20. There is no metadata endpoint; the browser derives the id range

## Context

[ADR 17](0017-image-fetch-timing.md) established that `/api/images` performs no
upstream I/O — every field it returns is derived from the request and from
configuration. It settled *when* images are fetched, and in doing so it made a
question visible that it did not ask: if the endpoint calls nothing and computes
only arithmetic, what is the round trip buying?

The metadata call returned a page number, a total, a count, and a list of ids.
The ids follow directly from the page and the count
([ADR 4](0004-bounded-catalogue.md) makes them derivable rather than stored), so
the entire payload is a function of two query parameters and two settings.

`/images/<id>` is unaffected by any of this and remains the only way image bytes
reach the browser ([ADR 3](0003-django-as-image-proxy.md)). What is in question
is solely the metadata hop that preceded it.

## Decision

**`/api/images` is removed. The shell publishes the catalogue bound and the page
size, and the client computes the id range for the current page.**

The shell renders the two values the arithmetic needs as data attributes, and
the client builds one placeholder tile per id:

    <div id="gallery"
         data-catalogue-size="100"
         data-page-size="10"
         data-image-url-template="/images/0">

    first = (page - 1) * count + 1
    ids   = first … min(first + count - 1, catalogueSize)

A tile's `src` is that template with the id substituted. The template is
produced by reversing the `image` route, so no path is written in JavaScript
and F5.4 still holds — the client substitutes an id into a server-built URL
rather than assembling one.

Page loading becomes one document request followed by N image requests. The
grid renders from markup the server already sent.

### The id is the seed, in two vocabularies

The browser knows a tile by its **id**. `provider.py` reads that same number as
picsum's **seed**. They coincide today and the translation still happens in one
place ([ADR 9](0009-url-vocabularies.md)), so a provider keyed on something else
would change `provider.py` and leave `/images/7` working. `seed` continues to
appear in no URL, payload, or rendered markup the browser can see.

## Consequences

**One fewer round trip before the first image.** ADR 17 accepted "two round
trips before the first pixel" as a real cost; this removes one of them. The
grid's structure is in the document, so tiles exist before any script has
fetched anything.

**Page arithmetic now runs in the browser as well as the server.** This is the
substantive cost, and it is a genuine departure from brief line 77's "all image
generation logic on the backend". The mitigating facts: the server still owns
the *bounds* — catalogue size and page size are settings the client is handed,
never values it decides — and it still validates every parameter at the document
boundary ([ADR 19](0019-validation-errors-carry-a-usable-payload.md)) and again
at `/images/<id>`. What moved is a multiplication, not a policy.

**Two implementations of the same range must agree.** The client computes ids to
render tiles; the server computes the same range when it validates a page number
against the catalogue. A divergence would show as tiles requesting ids the
server considers out of range. They are tested on both sides — `tests/unit/`
covers the Python, and the browser tier asserts the rendered ids — but this is
the coupling to watch, and it did not exist when one side computed and the other
consumed.

**F2.7 is unchanged in substance and changed in evidence.** "Each page composed
from multiple upstream calls" is still true: a page is N `/images/<id>` requests,
each producing its own upstream fetch. What is gone is the scenario asserting a
single metadata call, replaced by one asserting that rendering the grid reaches
no further than this application. The stage-2 scenario counting ten upstream
calls per page is untouched and remains F2.7's primary evidence.

**Per-image metadata has nowhere to live.** `width`, `height`, `grayscale`, and
`blur` — the resolved values [ADR 13](0013-module-structure.md) has the provider
return, and which F4.4's parameters panel renders — were going to ride on the
metadata payload. The detail view now gets them from `api_image`
(`/api/images/<id>`), which survives because it describes *one* image and cannot
be derived from arithmetic. The grid does not need them: a tile knows its id and
its `src`, and the display size is a CSS concern.

**The client cannot be told about a page it should not render.** Previously the
server could return an empty `images` list or a corrected page number in the
payload. Now an out-of-range page is caught only at the document boundary, by
the redirect. That path is tested directly, including that the corrected URL
does not itself redirect.

## Alternatives rejected

**Keep `/api/images`.** The endpoint the rest of the design was written around.
It keeps page arithmetic on the server, gives per-image metadata a home, and
satisfies brief line 77 without qualification. Rejected on the judgement that a
round trip returning arithmetic the client can do — with the catalogue bound
handed over anyway — is ceremony rather than architecture. This is the closest
call in the file, and if per-page metadata later needs a server-side decision
(a curated collection, ids that are not contiguous, a bound that varies per
request), this ADR should be reversed rather than worked around.

**Embed the id list in the shell as JSON.** The server computes the range and
renders it into the document, so no arithmetic runs in the browser and no round
trip is spent. Rejected because it makes the shell response page-specific, which
costs the ability to cache it, and it solves only the arithmetic — the client
still needs the catalogue bound for pagination controls.

**Server-render the tiles themselves.** The logical end of the same reasoning:
if the server knows the ids, it can emit the markup.
[ADR 2](0002-client-side-rendering.md) settled client-side rendering after a
round trip through the alternative, and reopening it is out of scope here.
