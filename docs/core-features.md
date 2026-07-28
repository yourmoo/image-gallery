# Core features

The brief's [Core Requirements](../django_image_gallery_assignment.md) (lines
38–82) enumerated as five numbered features. These IDs are the shared vocabulary
across this document, the Gherkin in [tests/features/](../tests/features/), and
the code.

Each row cites the brief line it comes from, so any requirement can be traced
back to its source.

## F1 — Image grid

| ID | Requirement | Brief |
| --- | --- | --- |
| F1.1 | Display a collection of images in a grid layout | 42 |
| F1.2 | Images generated dynamically through backend logic | 44 |
| F1.3 | Images vary by parameters such as size and visual filters | 45 |

## F2 — Pagination

| ID | Requirement | Brief |
| --- | --- | --- |
| F2.1 | Page state is URL-driven (query params) | 47 |
| F2.2 | Invalid page redirects to page 1 **and** shows a validation message | 48 |
| F2.3 | Pagination links preserve active filters and sizing | 49 |
| F2.4 | 10 images per page by default | 50 |
| F2.5 | Image count configurable by the user via UI | 43, 50 |
| F2.6 | Page 1 fetches images 1–10, page 2 fetches 11–20 | 51 |
| F2.7 | Each page composed from multiple upstream image calls | 26, 52 |

F2.7 is satisfied per tile rather than per page: the metadata call makes no
upstream request at all, and each of the page's N images is fetched by its own
`/images/{id}` request when the browser asks for it
([ADR 17](adr/0017-image-fetch-timing.md)).

## F3 — Image variations

| ID | Requirement | Brief |
| --- | --- | --- |
| F3.1 | Multiple named sizes (small, medium, large) | 58 |
| F3.2 | Normal (default) images | 59 |
| F3.3 | Grayscale rendering | 60 |
| F3.4 | Blur, intensity 0–10 | 61 |
| F3.5 | Grayscale and blur usable together | 64 |
| F3.6 | Invalid transformation values rejected with a clear error | 65 |

## F4 — Detail view

| ID | Requirement | Brief |
| --- | --- | --- |
| F4.1 | A detail view for individual images exists | 69 |
| F4.2 | Displays a larger version of the image | 71 |
| F4.3 | Reflects all active transformations | 72 |
| F4.4 | Shows the parameters used to generate the image | 73 |

## F5 — Backend-driven URL generation

| ID | Requirement | Brief |
| --- | --- | --- |
| F5.1 | All image generation logic on the backend | 77 |
| F5.2 | Templates never construct image URLs | 78 |
| F5.3 | URL generation centralised in a service layer | 79 |
| F5.4 | Django URL reversing for internal links | 80 |
| F5.5 | Upstream images cached while the app runs | 81 |

**F5.1–F5.4 have no Gherkin scenarios.** They are code-structure properties,
unobservable from outside the application: a hardcoded correct URL is
indistinguishable from a reversed one when viewed through a browser or a test
client. They are verified by unit tests that inspect structure directly. F5.5
*is* observable — a repeated request must not produce a second upstream call —
so it has a scenario.

## Decisions that shape these features

Four ambiguities in the brief were resolved before the Gherkin was written.
Each changes what a scenario asserts, so they are recorded here rather than left
implicit in the tests.

### Invalid transformation values (F3.6)

Brief line 65 says "reject with a clear validation error"; line 48 says bad
*pages* redirect and explain. Two different verbs for the same class of problem.

**Resolved:** the validation layer rejects the value, and the page recovers. An
invalid parameter falls back to its default, the gallery still renders `200`,
and a notice states what was ignored — for example *"'huge' is not a valid size
— showing medium."*

This satisfies "reject" at the boundary where rejection is meaningful, without
dead-ending a user who pasted a bad URL, and it stays consistent with how the
brief itself treats a bad page one section earlier.

### The collection is bounded

picsum.dev has no list endpoint (brief line 25), so nothing tells the
application how many images exist. Without a bound there is no last page, and
"out of range" cannot be specified or tested.

**Resolved:** `GALLERY_CATALOGUE_SIZE`, default 100.

The catalogue is **not a structure that gets built**. It is a single integer in
settings — there is no boot-time or first-request population step, no list, and
no allocation. Image ids are derivable, so the URL for id 47 is constructed on
demand and only the ids on the requested page are ever fetched. That is also
what makes F2.7 true: a page *is* several upstream calls, issued as the browser
requests each tile.

Consequences:

- **Multiple instances stay consistent** because each reads the same environment
  variable. There is no shared state to drift. This is the main argument for a
  configured bound over discovering one by probing upstream for a 404 — probing
  instances could genuinely disagree, and two containers behind one load
  balancer would report different total page counts.
- **Growing the catalogue is an operator config change plus a restart**, which
  is the shape brief line 96 asks for.
- **Catalogue size is deliberately not user-adjustable.** Only the per-page
  count is (F2.5). Exposing catalogue size to the browser would hand a client an
  unbounded upstream-fetch multiplier.

### Detail view size (F4.2 vs F4.3)

"Display a larger version" and "reflect all active transformations" contradict
each other whenever the user is browsing at `small`, if size counts as a
transformation.

**Resolved:** the detail view always renders at `large`; grayscale and blur
carry over from the gallery.

Size is a *presentation* choice belonging to its context — a grid wants small
images, a detail page wants a big one. Grayscale and blur are *content* choices
describing how the image should look anywhere. So "all active transformations"
means the filters, and "larger" governs size. The F4.4 parameters panel shows
the values actually used, so nothing is hidden from the user.

Rejected: stepping up one size (small→medium, medium→large), because `large` has
nowhere to go and the rule needs a special case.

### Invalid page and its message (F2.2)

The brief wants both a redirect and a user-facing message. There is no database,
so there are no sessions and no `django.contrib.messages`.

**Resolved:** the view validates, redirects to `?page=1&notice=invalid_page`,
and renders the banner from the query parameter. Stateless and bookmarkable.

Why the redirect is worth having rather than rendering page 1 in place:

- **URL truthfulness** — the address bar matches the content, so bookmarking,
  sharing, and refreshing all behave.
- **One canonical URL per page** — otherwise `?page=abc`, `?page=0`, and
  `?page=-5` all serve page-1 content at distinct URLs.
- **Recovery over refusal** — the rule's real content is "never dead-end a
  typo", and redirecting is the conventional way to express that.

## Two URL vocabularies

The client-facing URL contract is deliberately separate from the provider's.
picsum.dev has **no `id` parameter** — image identity is expressed as `seed`,
and dimensions are pixel values in the path. Both are provider vocabulary, so
neither reaches the client.

| Concept | Client → Django | Django → picsum |
| --- | --- | --- |
| Identity | `id`, 1…catalogue size | `seed` |
| Dimensions | `size=small\|medium\|large`, or `WxH` | `/{width}/{height}` |
| Grayscale | `grayscale=1` | `grayscale=1` |
| Blur | `blur=0…10` | `blur=0…10` |

    Client:    /images/7?size=large&blur=5
    Upstream:  https://picsum.dev/800/800?seed=7&blur=5

    Client:    /images/7?size=1200x900
    Upstream:  https://picsum.dev/1200/900?seed=7

Seeds are what make pagination meaningful: a seeded request returns the same
photograph every time, so page 3 is reproducible and a bookmark still works
tomorrow. Without a seed, every request returns a different image.

`grayscale` and `blur` sharing names across the two columns is coincidence, not
contract — they are translated like everything else. See
[ADR 9](adr/0009-url-vocabularies.md).

## Configuration

| Setting | Default | Feature |
| --- | --- | --- |
| `GALLERY_CATALOGUE_SIZE` | 100 | Bounded collection |
| `GALLERY_DEFAULT_PAGE_SIZE` | 10 | F2.4 |
| `GALLERY_DEFAULT_SIZE` | medium | F3.2 |
| `GALLERY_SIZE_SMALL` | 200x200 | F3.1 |
| `GALLERY_SIZE_MEDIUM` | 400x400 | F3.1 |
| `GALLERY_SIZE_LARGE` | 800x800 | F3.1 |
| `GALLERY_MAX_DIMENSION` | 1600 | F3.1, bounds custom sizes |
| `GALLERY_MIN_DIMENSION` | 16 | F3.1, bounds custom sizes |
| `GALLERY_UPSTREAM_TIMEOUT` | 5.0 | Resilience |
| `GALLERY_UPSTREAM_RETRIES` | 2 | Resilience |
| `GALLERY_UPSTREAM_BACKOFF` | 0.2 | Resilience |
| `GALLERY_CACHE_TTL` | 300 | F5.5, freshness window |
| `GALLERY_CACHE_RETENTION` | 3600 | Stale fallback window |
| `GALLERY_CACHE_MAX_ENTRIES` | 300 | Bounds worker memory |

Allow-lists, per brief line 155:

| Parameter | Accepted values |
| --- | --- |
| `size` | `small`, `medium`, `large`, or `WxH` within the dimension bounds |
| `blur` | integers 0–10 |
| `grayscale` | on / off |
| `count` | 10, 20, 50 |
| `page` | integers 1 … *catalogue size ÷ count* |

The named sizes resolve to configured pixel dimensions, and the same bounds
apply to both forms — a named size configured outside them fails at startup
rather than silently exceeding the ceiling. Out-of-range custom dimensions are
rejected and fall back to the default with a notice; they are **not clamped**,
because silently serving 1600 when 6000 was requested is a substitution the user
cannot detect. See [ADR 10](adr/0010-configurable-and-custom-sizes.md).
