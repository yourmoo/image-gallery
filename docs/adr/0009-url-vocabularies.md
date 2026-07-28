# 9. Two URL vocabularies, translated at the service layer

## Context

[ADR 3](0003-django-as-image-proxy.md) established that the browser never
contacts picsum.dev. That prevents the provider's *hostname* from reaching the
client, but it does not by itself prevent the provider's *vocabulary* from
doing so.

Investigating the provider's API surface made the distinction concrete. picsum.dev
has **no `id` parameter**. Image identity is expressed with `seed`:

    https://picsum.dev/400/400?seed=7

Verified behaviour: `seed=7` returns a byte-identical image on every request,
the same photograph at 200, 400, and 800 pixels, and transformations apply to
that same image. Without a seed, every request returns a different picture.

That makes `seed` essential — pagination is meaningless if page 3 shows
different photographs on every load. But `seed` is picsum's word for the
concept. Exposing it in client-facing URLs would mean that swapping to a
provider using `id`, `photo_id`, or a UUID either changes every client URL and
bookmark, or keeps a parameter named after a provider no longer in use.

Dimensions carry the same risk in a sharper form: picsum takes pixel dimensions
in the path (`/800/800`) and has no concept of "large".

## Decision

Two URL vocabularies, translated at exactly one place — the service layer.

| Concept | Client → Django | Django → picsum |
| --- | --- | --- |
| Identity | `id`, integer 1…catalogue size | `seed` |
| Dimensions | `size=small\|medium\|large` | `/{width}/{height}` in pixels |
| Grayscale | `grayscale=1` | `grayscale=1` |
| Blur | `blur=0…10` | `blur=0…10` |

    Client:    /images/7?size=large&blur=5
    Upstream:  https://picsum.dev/800/800?seed=7&blur=5

The client-facing vocabulary is the **stable contract**. The upstream
vocabulary is an implementation detail that may change with the provider.

The id → seed mapping begins as identity (id 7 → seed 7). That is deliberate,
not an omission: it is the seam where a different provider's identity scheme
would be absorbed.

## Consequences

**Named sizes are the substantive translation.** `small|medium|large` is this
application's vocabulary; picsum has only pixel dimensions. The mapping
(`large` → 800×800) lives in the service layer beside the size tokens, so a
provider expressing sizes differently changes one table and nothing else.

**`grayscale` and `blur` sharing names with picsum's parameters is a
coincidence, not a contract.** They are translated like everything else. Code
must not forward the client's query string to the provider, even where the names
happen to match — that would silently couple the two vocabularies and the next
provider change would break in a way the tests do not catch.

**Client URLs survive a provider change.** Bookmarks, pagination links, the
Gherkin, and the tests are all written in the client vocabulary, so replacing
the provider touches the service layer and its unit tests only. This is the
concrete form of the brief's line 91 requirement.

**The catalogue is a seed range.** `GALLERY_CATALOGUE_SIZE` bounds ids 1…100,
each mapping to a seed. This reinforces [ADR 4](0004-bounded-catalogue.md):
nothing is enumerated, because an id is translated to a seed on demand and only
the ids on the requested page are ever fetched.

**Stable images make pagination meaningful.** Because seeds are deterministic,
page 3 shows the same photographs tomorrow. A bookmarked gallery page is
reproducible — without which requirement F2.1's URL-driven state would be
hollow.

**One translation point to test.** The mapping is a pure function from client
parameters to an upstream URL, testable without network access, and it is where
`test_` coverage for requirement F5.3 concentrates.

## Alternatives rejected

**Expose `seed` directly in client URLs.** Simplest, and honest about what the
value is. Rejected because it hard-codes a provider concept into the public URL
contract — the precise coupling [ADR 3](0003-django-as-image-proxy.md) exists to
prevent, and it would make "replaceable with minimal changes" false for any
provider not using seeds.

**Forward the client query string to the provider unchanged.** Tempting because
`grayscale` and `blur` already match. Rejected because the match is
coincidental; it would couple the vocabularies invisibly and break on the next
provider whose parameters differ.

**Expose pixel dimensions instead of named sizes.** More flexible for the
client. Rejected because the brief asks for named sizes (line 58), and because
unbounded dimensions in a client URL is an unbounded upstream fetch multiplier —
the same denial-of-service concern that keeps catalogue size out of the UI in
[ADR 4](0004-bounded-catalogue.md).

**A UUID or opaque token as the client-facing id.** Hides the mapping
completely. Rejected as ceremony: the brief requires "page 1 must fetch images
1-10" (line 51), which sequential integer ids express directly and opaque tokens
obscure.
