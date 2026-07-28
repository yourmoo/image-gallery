# 5. The service layer owns the provider

## Context

Brief lines 87–92 ask for a clear abstraction over picsum.dev, API-specific
logic kept out of views and templates, a provider replaceable with minimal
changes, and a module structure separating service, transformations,
validation, and views. Lines 77–79 add that URL generation must be centralised
in a service-layer component.

The failure mode this guards against is familiar: the first version builds the
upstream URL inline in a view because it is two lines, the second version copies
those two lines into the detail view, and by the third the provider's URL format
is spread across the codebase and "replaceable with minimal changes" is false.

## Decision

One component owns every interaction with the image provider. Views ask it for
what they need and receive results; they never construct an upstream URL, never
know the provider's URL format, and never import an HTTP client.

The boundary is the **provider**, not merely HTTP. Transformation semantics —
what "large" means in pixels, how grayscale and blur are expressed — belong
behind it, because they are provider vocabulary.

## Consequences

**Views become thin.** A view validates input, calls the service, and renders.
That is what makes the views testable without network access and the service
testable without Django.

**Requirement F5.2 is enforceable.** Because templates receive finished URLs
through context, a template *cannot* construct one — there is nothing in scope
to construct it from.

**F5.1–F5.4 are verified by unit tests, not Gherkin.** These are
code-structure properties, unobservable from outside the application: a
hardcoded correct URL is indistinguishable from a reversed one when viewed
through a browser or a test client. They need tests that inspect structure
directly. F5.5 is the exception — caching is observable, because a repeated
request must not produce a second upstream call, so it has a scenario.

**Provider replacement is a bounded change.** Swapping picsum.dev touches the
service and its tests; templates, views, and URL patterns are unaffected. This
is the claim line 91 makes, and confining provider knowledge is what makes it
true rather than aspirational.

**Django URL reversing for internal links** (line 80) sits on the other side of
this boundary. Internal routes are reversed; upstream URLs are built by the
service. Both are "URL generation" but they are different concerns, and the
service layer is where the distinction is kept honest.

## Alternatives rejected

**Build URLs in views.** Two lines the first time, duplicated by the third view,
and provider format leaks across the codebase. Directly contradicts line 79.

**A template filter or tag that builds image URLs.** Convenient, and it keeps
views thin — but it is exactly what line 78 forbids, and it moves provider
knowledge into the least testable layer.

**A thin HTTP wrapper only, with transformation logic in views.** Draws the
boundary at HTTP rather than at the provider. Transformation vocabulary is
provider-specific, so this splits one concern across two layers and leaves views
knowing how picsum expresses blur.

## Still open

The **module structure within** this boundary — where exactly the lines fall
between service, transformations, validation, and the HTTP client — is not yet
decided. See [the open questions](README.md#open-questions).
