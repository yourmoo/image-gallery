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
  parameter (`?notice=...`) on first load, and from the API's error payload
  thereafter.
- **Loading state is explicit.** Because the client knows when a fetch is in
  flight, the indicator covers pagination and filter changes, not only the
  initial load.

## What already exists

`static/css/app.css` establishes the vocabulary to build on. Do not start a
parallel system:

- Custom properties `--bg`, `--fg`, `--muted`, `--border`
- `color-scheme: light` — **light only**, no dark override (see Handover below)
- `main` capped at `70rem`, centred; `.site-header` with a bottom rule
- System font stack

`templates/base.html` provides `title`, `heading`, and `content` blocks.
`data-testid` attributes are already used as test hooks — keep adding them for
anything a test needs to find, so tests never depend on styling classes.

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

**Detail page parameters panel** (F4.4) — shows identifier, size, grayscale
state, and blur value. It reports what was *actually used*, which means size
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

## Handover — resolve before building

[design-system.md](design-system.md) is the asset layer for this file, and it
has **diverged from the CSS actually on disk**. The three items below are
blocking: each one has a developer reaching for something that is documented but
absent, or building against markup that does not match the architecture.

Everything else in both documents stands. This is reconciliation, not a redesign
— the component inventory, the error matrix, and the state rules are all correct
and should be preserved as they are.

### 1. Light only — dark mode is removed

**Decided.** The interface is light only. `design-system.md` Principle 6 is
correct; `tokens.css` and this file were stale and have been corrected here.

To action in [`static/css/tokens.css`](../../image_gallery/static/css/tokens.css):

- Change `color-scheme: light dark` (line 14) to `color-scheme: light`.
- Delete the whole `@media (prefers-color-scheme: dark)` block (lines 92–117).
- Keep the `prefers-reduced-motion` block. That one stays.

No `app.css` change is needed — it carries no dark rules.

### 2. Tokens: the doc and the CSS are different designs

`design-system.md` documents a palette and scale that `tokens.css` does not
implement. Not drift at the margins — the core values differ:

| Token | design-system.md | tokens.css |
| --- | --- | --- |
| `--bg` | `#FDFDFC` | `#ffffff` |
| `--accent` | `#3B6EA8` | `#1f5fa8` |
| `--radius-sm` | 6px | 3px |
| `--radius` | 8px | 6px |
| `--duration` | 160ms | 200ms |
| `--ease` | `ease-out` | `cubic-bezier(0.2, 0, 0.2, 1)` |
| Spacing | 8 steps, 4–56px | 7 steps, in `rem` |
| `--text-xl` | 44px | 1.25rem (20px) |
| Notices | cool/blue, plus a separate `--warn` family | one warm amber family |

**Absent from `tokens.css` entirely** — every one of these is referenced by a
component in `design-system.md`:

`--accent-ink`, `--placeholder-alt`, `--warn`, `--warn-bg`, `--warn-border`,
`--space-8`, `--text-xs`, `--radius-pill`

The `--warn` family is the one that hurts: the failed-tile state depends on it,
that state is mandatory (a failed tile must never look like a loading tile), and
it has its own entry in the verification checklist.

**Take `design-system.md` as the intent and bring `tokens.css` up to it** — it
is the newer and more complete design, and it is the one reasoned through the
light-only palette. Preserve `--bg`, `--fg`, `--muted`, `--border` by name; the
baseline markup already uses them.

### 3. The markup blocks are server-rendered; the app is not

Every component block in `design-system.md` is written in Django template syntax
— `{% url 'gallery' %}`, `{{ image.url }}`, `{{ grayscale|yesno:"on,off" }}`,
`{% if has_previous %}`. The application is **client-side rendered**
([ADR 2](../adr/0002-client-side-rendering.md), and settled). JavaScript fetches
JSON and builds the DOM.

The structure of those blocks is right and should be kept. What has to change is
the framing:

- Rewrite them as **plain HTML**, with a note on which attributes JavaScript
  sets at runtime (`data-active`, `data-loaded`, `data-size`, `src`, `href`).
- **The controls block is the one that actively misleads.** It is a
  `<form method="get" action="…">` with an Apply button. Under CSR there is no
  form submit — controls fire a `fetch` and call `history.pushState`. Whether an
  Apply button exists at all is an open design question: instant-apply on change
  is the more usual CSR pattern, but it fires a request per keystroke on the
  blur field. **Decide this and write it down.**
- Pagination `{% if %}` guards become "JS renders no element at all" — the
  Gherkin asserts *absence*, not a disabled state.

### 4. Not yet specified

Lower priority than the three above, but needed before the UI is finished:

- **No JS module or state structure.** CSR means something owns URL↔state sync,
  the fetch lifecycle, and the render loop. Nothing describes how that is
  organised, and it is the largest unwritten piece of the front end.
- **No markup for the failure states.** The failed tile, degraded banner, empty
  state, and unreachable page are described in prose only, while every other
  component gets a markup block. They carry real requirements and deserve the
  same treatment.
- **`--image-*` tokens are ambiguous under custom sizes.** The comment reads
  "CSS display dimensions; the proxy serves matching pixel dimensions", but
  custom `WxH` sizes ([ADR 10](../adr/0010-configurable-and-custom-sizes.md)) mean
  the display size is not always one of the three named values.

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
