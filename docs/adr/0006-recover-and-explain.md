# 6. Invalid parameters recover and explain

## Context

The brief specifies two different responses to bad input, one section apart:

- **Line 48**, for pages: redirect to page 1 *and* display a user-facing
  validation message.
- **Line 65**, for transformations: "reject invalid transformation values with a
  clear validation error."

"Reject" and "redirect and explain" are different verbs for the same class of
problem — a user arriving with a parameter the application cannot honour. Taken
literally, `?page=abc` gets a working gallery and `?size=huge` gets an error
page.

There is a second problem specific to this application: with no database there
are no sessions and no `django.contrib.messages`
([ADR 1](0001-no-database.md)), so there is no conventional mechanism for a
message to survive a redirect.

## Decision

**Invalid input is rejected at the validation boundary and recovered in the
UI.** The invalid value never reaches the provider; the parameter falls back to
its default; the user sees a working gallery with a notice stating what was
ignored.

The two consumers differ, per [ADR 2](0002-client-side-rendering.md):

| Consumer | Response |
| --- | --- |
| JSON API | **400** with a machine-readable error naming the parameter and value |
| Browser UI | Renders with the fallback applied, plus a notice |

The client makes this coherent: it calls the API, receives the validation error,
re-requests with defaults, and displays the notice. A program gets a real
rejection it can act on; a person who pasted a bad URL gets a gallery and an
explanation.

For an invalid page specifically, brief line 48 requires a redirect. On the
initial document request — where a bad URL can be pasted or bookmarked — the
shell view redirects, carrying the notice as a query parameter:

    GET /?page=abc  →  302  →  /?page=1&notice=invalid_page

For in-app navigation, where no document request occurs, the client corrects the
URL with `history.replaceState` and shows the same notice. Both paths call the
same validator, so the rule is defined once.

Validation uses allow-lists, per line 155:

| Parameter | Accepted |
| --- | --- |
| `size` | `small`, `medium`, `large` |
| `blur` | integers 0–10 |
| `grayscale` | on / off |
| `count` | 10, 20, 50 |
| `page` | 1 … catalogue ÷ count |

## Consequences

**One bad parameter does not discard the good ones.** `?size=enormous&blur=6`
renders at the default size with blur 6 applied, and explains only the size. The
Gherkin asserts this directly.

**Several parameters can be invalid at once**, so the notice is a list rather
than a single string. The design system's notice component is built for that.

**The notice travels in the URL.** A direct consequence of having no sessions.
It is stateless and bookmarkable; the cost is a slightly noisier URL after a
correction.

**A user is never dead-ended by a typo.** Someone who pastes a mangled URL sees
the gallery and an explanation, not an error page.

**"Reject" is honoured where it is meaningful.** The value is genuinely rejected
— it never reaches the service or the provider. What differs from a literal
reading is the *response*: recovery rather than refusal.

**Not every bad input recovers.** A nonexistent image id returns 404 — see
[ADR 7](0007-detail-view-size.md). The distinction: a bad transformation has a
sensible default to fall back to, while a request for image 101 in a 100-image
catalogue has no sensible substitute. Silently showing image 1 would be worse
than saying it does not exist.

## Alternatives rejected

**400 with an error page.** The literal reading of "reject". Rejected because it
is inconsistent with how the brief itself handles a bad page one section
earlier, and because it dead-ends a user over a typo in a query string.

**A single behaviour for both API and UI.** Simpler to specify. Rejected because
[ADR 2](0002-client-side-rendering.md) makes them genuinely two consumers with
different needs: a program calling `/api/images?size=huge` should receive a 400
it can act on, while a person who pasted that URL should get a working gallery
and an explanation. See the split recorded in the Decision above.

**Render page 1 in place without redirecting.** Fewer moving parts, and it
removes the need to carry a message across a redirect entirely. Rejected
because line 48 explicitly asks for a redirect, and because the redirect earns
two things worth having: the address bar matches the content, and there is one
canonical URL per page rather than `?page=abc`, `?page=0`, and `?page=-5` all
serving page-1 content at distinct URLs.

**A short-lived cookie for the message.** Keeps the URL clean, but adds hidden
state to an application whose defining property is that it has none.
