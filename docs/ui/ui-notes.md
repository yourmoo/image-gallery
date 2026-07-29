# UI notes

The design brief for the visual layer. The Gherkin in
[tests/features/](../../tests/features/) specifies *behaviour* and deliberately
says nothing about appearance — it asserts "the images are rendered in
grayscale", never what the grayscale control looks like. This file fills that
gap: the controls that must exist, the states each one needs, and the
constraints they work within.

Requirement IDs referenced here are defined in [core-features.md](../core-features.md).

## Constraints

From the brief (lines 158–163):

- Simple, clear, and functional. **Usability over visual complexity** — this is
  an explicit instruction, not a fallback. Restraint is the brief.
- Responsive across mobile, tablet, and desktop.
- A loading indicator while gallery images are downloading.

From the architecture:

- **Client-side rendered.** JavaScript fetches JSON and builds the DOM. Controls
  update state without a full page reload, and the URL is kept in step with
  `history.pushState` so every view stays linkable
  ([ADR 2](../adr/0002-client-side-rendering.md)).
- **Django is an image proxy.** Every `<img src>` points at Django, never at
  picsum.dev. No provider URL appears in any payload or rendered markup.
- **No database**, so no sessions — the validation notice arrives as a query
  parameter (`?notice=...`), set by the `index` redirect on first load and by
  `history.replaceState` for in-app corrections. It never comes from the API:
  the client builds requests from its own allow-listed controls, so a `400`
  means the client has a bug
  ([ADR 19](../adr/0019-validation-errors-carry-a-usable-payload.md)).
- **The grid is derived, not fetched.** There is no page-metadata call: the
  shell publishes the catalogue size and page size, and the client computes the
  id range for the current page
  ([ADR 20](../adr/0020-ids-are-derived-in-the-browser.md)). Changing the count
  is therefore instant — no round trip is needed to know which tiles to draw.
- **Loading state is explicit.** Because the client knows when a fetch is in
  flight, the indicator covers pagination and filter changes, not only the
  initial load.

## What already exists

`static/css/tokens.css` holds every primitive and `static/css/app.css` the
components built from them. Nothing hardcodes a value. Do not start a parallel
system:

- The full palette, spacing, type, radius, and motion scales of
  [design-system.md](design-system.md), which `tokens.css` was reconciled with
  on 2026-07-29
- `color-scheme: light` — **light only**, no dark override
- `main` capped at `70rem`, centred; `.site-header` with a bottom rule
- Components for the grid, tiles (pending, loaded, failed), notices (cool and
  warm), pagination, controls, and the detail view

`templates/base.html` provides `title`, `heading`, and `content` blocks;
`index.html` is the gallery shell and `detail.html` the single-image page.

`data-testid` attributes are the contract the browser suite binds to — keep
adding them for anything a test needs to find, so tests never depend on styling
classes. The full list is documented at the top of
[tests/e2e/test_gallery_steps.py](../../tests/e2e/test_gallery_steps.py) and
[tests/e2e/test_detail_steps.py](../../tests/e2e/test_detail_steps.py).

## Control inventory

Everything the Gherkin requires a user to be able to do. This is the complete
set — no scenario needs a control not listed here.

| Control | Values | Requirement |
| --- | --- | --- |
| Size | small, medium, large — **medium is default** | F3.1, F3.2 |
| Grayscale | on / off, default off | F3.3 |
| Blur | integer 0–10, default 0 | F3.4 |
| Image count | 10, 20, 50, **10 is default** | F2.5 |
| Pagination | previous / next, page indicator | F2.1, F2.3 |
| Image link | each grid image opens its detail page | F4.1 |
| Back to gallery | detail → gallery, preserving page and filters | F4.1 |
| Detail size | small, medium, large — **large is the default**, not a rule | F4.4 |
| Detail grayscale | on / off, inherited from the gallery | F4.3, F4.4 |
| Detail blur | integer 0-10, inherited from the gallery | F4.3, F4.4 |

The detail page has its own copies of size, grayscale, and blur. They are not
the gallery's: a choice made there stays there, so opening one image at `small`
does not re-render the grid on return
([ADR 7](../adr/0007-detail-view-size.md) § Amendment). Its size arrives as
`?detail_size=`, distinct from the gallery's `?size=` for exactly that reason.

Size, grayscale, blur, and count belong to **one form**. They are read together
on submit, so changing two at once is a single navigation. Blur and grayscale
must be combinable (F3.5).

The count control must be a **real control on the page** (F2.5 says "by the
user via UI"), not merely a query parameter. This is the requirement most
easily under-delivered.

## States each control needs

The scenarios assert several of these directly, so they are not optional
polish.

**Every control** — default (nothing chosen), active (a non-default value
chosen, and it must be visible *which* value is active on page load, since the
form is re-rendered from the URL on every navigation), and focus-visible for
keyboard use.

**Pagination** — `previous` is absent or disabled on page 1; `next` is absent or
disabled on the last page. Both are asserted:

    Then there is no link to a next page
    Then there is no link to a previous page

Prefer rendering no link at all over a disabled-looking link, so the assertion
is about presence rather than an ARIA state.

**Notice banner** — shown when `?notice=` is present. Two distinct causes, and
they read differently:

| Cause | Message shape |
| --- | --- |
| Invalid page (F2.2) | "That page doesn't exist — showing page 1." |
| Invalid parameter (F3.6) | "'huge' is not a valid size — showing medium." |

Multiple parameters can be invalid at once. The banner must handle a list, and
one bad parameter must not discard the good ones alongside it:

    Scenario: A valid filter survives an invalid one

The banner is informational, not an error page — the gallery renders normally
beneath it. Dismissible is fine; it must not be the only way to continue.

**Loading indicator** (line 163) — client-side rendering makes this direct: the
application knows when a fetch is in flight, so the state is explicit rather
than inferred.

Two distinct loading states, and they must not be conflated:

| State | When | Treatment |
| --- | --- | --- |
| Fetching the page | Navigating, filtering, changing count | Indicator over the grid area; keep the previous grid visible and dimmed rather than blanking it |
| Fetching each image | After the JSON arrives, per tile | Fixed aspect-ratio placeholder that fades to the image |

Per-tile placeholders remain worthwhile even with an explicit indicator: each
`<img>` is a separate request through the proxy, and a 50-image page at medium
is roughly 1 MB. The placeholder reserves layout so the grid never reflows.
Set `width`/`height` and use `loading="lazy"` below the fold.

**A failed tile must not look like a loading tile.** The design system carries
`--warn` tokens for exactly this distinction.

**Detail page parameters panel** (F4.4) — **reports and sets**. Each row pairs
the resolved value with the control that changes it, so the two cannot
disagree. Shows identifier, size, grayscale state, and blur value.

It is a real `<form>` with a submit button, because this page is
server-rendered and must work without JavaScript. `detail-panel.js` then hides
the button and makes each control apply on change, so the page matches the
gallery's instant-apply behaviour when script is available. It reports what was *actually used*, which means size
reads `large` even when the gallery was showing `small`:

    Given I am viewing the gallery at the "small" size
    ...
    Then the page shows the size "large"

That is intentional, and the panel is where a user finds out. Present it as a
plain description list, not a decorative caption.

## Layout

**Grid** — responsive columns via `repeat(auto-fill, minmax(...))` so the count
adapts to viewport rather than to breakpoints. Note the grid must hold 10, 20,
or 50 images; at 50 on mobile, image dimensions matter more than column count.

**Controls** — above the grid, wrapping on narrow screens. They must not push
the first row of images off a phone screen.

**Detail page** — image and parameters panel; side by side on wide viewports,
stacked on narrow. Include the back link at a predictable position.

## Reconciliation — resolved

[design-system.md](design-system.md) is the asset layer for this file. The two
had diverged badly enough that three items were listed here as **blocking**:
tokens a component referenced but the CSS did not define, a palette that was a
different design rather than a drifted one, and markup written in Django
template syntax for an application that renders in the browser.

**All three were resolved while building the gallery, 2026-07-29.** The record
is kept because the reasoning still matters — particularly which document won,
and why.

### `design-system.md` was the more accurate document

Twice, and it is worth stating plainly: when the CSS on disk disagreed with the
design system, **the design system turned out to be right**.

- The token palette. `tokens.css` carried a different `--bg`, `--accent`,
  radius scale, and motion timing, and was missing `--accent-ink`,
  `--placeholder-alt`, the whole `--warn` family, `--space-8`, `--text-xs`, and
  `--radius-pill`. The document was taken as the intent and the CSS brought up
  to it, preserving `--bg`, `--fg`, `--muted`, and `--border` by name because
  the baseline markup already used them.
- The URL split. The design system's component blocks had `/images/<id>` for
  the detail **page** and `/img/<id>` for the image **bytes** from the start.
  The proxy was built on `/images/<id>`, which collided with the detail page —
  one path cannot be both. The design system had it right and the code moved.

The `--warn` family was the one that mattered most: the failed-tile state
depends on it, and that state is mandatory, since a failed tile must never look
like one still loading. It is now `--warn-bg` with a dashed `--warn-border`,
against a striped neutral placeholder — visibly different at a glance.

### The markup blocks are plain HTML

They were Django template syntax; they are now plain HTML with a note on which
attributes JavaScript sets at runtime. The structure was always right.

**Controls apply instantly — decided, and built.** No Apply button: under CSR
there is no submit, and a control fires a navigation on `change`.

Blur turned out not to need the debounce this section originally specified.
A range fires `input` continuously while dragging and `change` once when the
drag ends, so the readout updates on `input` (free, no network) and the
navigation happens on `change`. Dragging the slider costs one request rather
than eleven, with no timer to tune.

### Still unspecified

- **The `--image-*` tokens are ambiguous under custom sizes.** The comment
  reads "CSS display dimensions; the proxy serves matching pixel dimensions",
  but a custom `WxH` size ([ADR 10](../adr/0010-configurable-and-custom-sizes.md))
  is not one of the three named values. In practice the grid falls back to
  `--cell-medium` and the served dimensions govern; the tokens name the common
  cases rather than every case.
- **The empty state and the unreachable page** have no markup block. Neither is
  reachable in the current application — the catalogue is a configured constant
  and every failure degrades per tile — so they are unwritten rather than
  missing. The failed tile and degraded banner, which *are* reachable, are both
  built and covered by scenarios.

The JS module structure this section once listed as unwritten now exists:
`static/js/derive.js` holds the pure logic and is unit-tested without a DOM,
and `static/js/gallery.js` holds the DOM wiring. See
[tests/unit/js/README.md](../../tests/unit/js/README.md).

## Out of scope

- Sorting, infinite scroll, or lightbox behaviour — none are in the brief, and
  each adds state the URL would have to carry.
- Client-side filtering of an already-fetched page. Filters are server
  parameters: they change which images are fetched, not which are displayed.
- Animation beyond the image fade-in and the loading transition.
- Theming controls **and dark mode**. The interface is light only. Colour is the
  only theme-dependent layer, so if dark ever returns it redefines colour tokens
  and nothing else.
- A no-JavaScript fallback. The application requires JavaScript
  ([ADR 2](../adr/0002-client-side-rendering.md)); this is an accepted consequence,
  not an oversight.
