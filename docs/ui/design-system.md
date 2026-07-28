# Design system — Django Image Gallery

The concrete asset layer. [ui-notes.md](uploads/ui-notes-f42e73ad.md) says *what*
the interface must do; this file is *what to build it from* — the tokens, the
components, the markup each component expects, and the state each one needs.

Building a page should be assembly, not invention. If a value is needed that no
token provides, add the token here rather than hardcoding it in a template.

Requirement IDs (F2.x, F3.x, F4.x) refer to `core-features.md`.

| File | Contains |
| --- | --- |
| `static/css/tokens.css` | Every primitive value. Styles nothing. |
| `static/css/app.css` | Components, built only from tokens. |
| `static/js/state.js` | URL ↔ state, the single source of truth |
| `static/js/api.js` | Fetches JSON from Django |
| `static/js/render.js` | State → DOM |
| `static/js/main.js` | Wiring: events, fetch lifecycle, history |

`app.css` imports `tokens.css`, so templates link one stylesheet, exactly as
`base.html` already does.

**Architecture:** client-side rendered ([ADR 2](adr/0002-client-side-rendering.md)).
JavaScript fetches JSON and builds the DOM; the URL is kept in step with
`history.pushState`. JavaScript is required — that is an accepted consequence,
not an oversight — so this system does not carry no-JS fallbacks. Django remains
an image proxy: every `<img src>` points at Django, never at picsum.dev.

---

## Handover items — resolved

The four blocking items in ui-notes are settled here. Recorded so nobody
re-opens them.

1. **Light only.** `color-scheme: light`; no `prefers-color-scheme: dark` block.
   `prefers-reduced-motion` stays.
2. **Tokens.** This document is the intent; `tokens.css` is brought up to it (§2).
   `--bg`, `--fg`, `--muted`, `--border` keep their names — baseline markup uses
   them.
3. **Markup is plain HTML.** No Django template syntax. Each block marks which
   attributes JavaScript sets at runtime.
4. **Controls apply instantly. There is no Apply button.** Decided — see
   §Controls for the debounce rule that makes the blur field safe.

---

## 1. Principles

1. **Tokens are the only source of values.** No hardcoded colour, spacing, or
   size in a component or template. "Large" then means one thing across the
   grid, the detail view, and the docs.
2. **Restraint is the brief.** Usability over visual complexity — an explicit
   instruction, not a fallback. One elevation step, one accent, one focus
   treatment.
3. **The URL is the state.** Every view is linkable; every state change writes
   to the URL. Nothing is reachable only by clicking.
4. **One accent, two meanings.** Accent means *this value is not the default* or
   *this element has focus*. Neutrals carry everything else.
5. **Failure never looks like loading, and the two loadings never look alike.**
   Three distinct treatments: page-fetch, image-fetch, failed.
6. **Light only.** Colour is the only theme-dependent layer, so if dark ever
   returns it redefines colour tokens and nothing else.

---

## 2. Tokens

### Colour

| Token | Value | Role |
| --- | --- | --- |
| `--bg` | `#FDFDFC` | Page background |
| `--surface` | `#F2F2EF` | Recessed panels: controls bar, parameters panel |
| `--surface-raised` | `#FFFFFF` | Cards and fields sitting on a surface |
| `--fg` | `#1B1B19` | Body text, primary fill |
| `--muted` | `#6E6E68` | Labels, captions, secondary text |
| `--border` | `#E2E2DD` | Default hairlines |
| `--border-strong` | `#D8D8D2` | Interactive borders: fields, pagination links |
| `--accent` | `#3B6EA8` | Links, active state, focus ring |
| `--accent-fg` | `#FFFFFF` | Text on accent |
| `--accent-subtle` | `#EDF2F9` | Filter chips, accent-tinted hover |
| `--accent-ink` | `#2C5385` | Text on `--accent-subtle` |
| `--notice-bg` / `--notice-border` | `#F5F8FC` / `#DFE6F0` | Validation banner |
| `--warn` | `#B08442` | Degraded / failed marker |
| `--warn-bg` / `--warn-border` | `#FCF8F0` / `#EADFC8` | Degraded banner, failed tile |
| `--placeholder` / `--placeholder-alt` | `#F2F2EF` / `#EAEAE6` | Tile before load (135° stripe) |

**Nothing here is red**, because nothing in this system is an unrecoverable
error page. The validation banner is cool/blue — it reports what *you* asked for
and fell back from, and the gallery renders normally beneath it. The degraded
banner is warm — it reports what the *system* did when upstream was unavailable.

### Spacing

`--space-1` … `--space-8` = **4, 8, 12, 16, 24, 32, 48, 56px**. Section padding
`--space-8`; label/content gap `--space-7`.

### Type

System font stack throughout.

| Token | Size / weight | Use |
| --- | --- | --- |
| `--text-xs` | 12 / 600, `0.08em`, uppercase | Eyebrows, table headers |
| `--text-sm` | 14 / 400 | Labels, captions, notices, controls |
| `--text-base` | 16 / 400, 1.6 | Body |
| `--text-lg` | 24 / 500, `-0.01em` | Section heading |
| `--text-xl` | 44 / 500, `-0.02em` | Page heading |

`--font-mono` (`ui-monospace, SFMono-Regular, Menlo, monospace`, 13px) is for
parameter *values*, identifiers, and token names, so numbers align and read as
data. Never for prose. Nothing below 12px. `text-wrap: pretty` on prose.

### Shape, elevation, motion

`--radius-sm` 6px (fields, buttons, tiles), `--radius` 8px (panels, cards,
banners), `--radius-lg` 12px (detail image), `--radius-pill` 999px (chips).
Borders always 1px. One `--shadow`: `0 1px 2px rgb(0 0 0 / 0.04)`.

`--duration` 160ms and `--ease` `ease-out`, both resolving to `0ms` under
`prefers-reduced-motion` so the fade honours the setting with no extra rules.
The image fade and the grid dim are the only animations in the system.

**Focus:** `outline: 2px solid var(--accent); outline-offset: 2px`. Never
removed, never replaced by a colour change alone.

### Gallery scales

| Token | Value | Use |
| --- | --- | --- |
| `--image-small` / `--image-medium` / `--image-large` | 200 / 400 / 800px | The named sizes of F3.1 |
| `--cell-small` / `--cell-medium` / `--cell-large` | 140 / 200 / 280px | Minimum grid cell per size |

Cell floors drive `repeat(auto-fill, minmax(var(--cell-*), 1fr))`, so **column
count follows viewport width rather than breakpoints** — one rule serves mobile,
tablet, and desktop. Single exception: below 480px the floor drops to **110px**,
because at 50 images on a phone image dimensions matter more than column count.

**Custom `WxH` sizes** ([ADR 10](adr/0010-configurable-and-custom-sizes.md)) are
not one of the three named values. For those, JavaScript sets
`--cell-custom` inline on the grid element from the requested width (clamped to
110–320px) and sets `data-size="custom"`; the `--image-*` tokens are not
consulted. The named tokens describe the three presets only.

### Reconciling `tokens.css`

These differed on disk. This document wins; update the CSS.

| Token | Was | Now |
| --- | --- | --- |
| `--bg` | `#ffffff` | `#FDFDFC` |
| `--accent` | `#1f5fa8` | `#3B6EA8` |
| `--radius-sm` / `--radius` | 3px / 6px | 6px / 8px |
| `--duration` / `--ease` | 200ms / `cubic-bezier(0.2, 0, 0.2, 1)` | 160ms / `ease-out` |
| Spacing | 7 steps in `rem` | 8 steps, 4–56px |
| `--text-xl` | 1.25rem | 44px |
| Notices | one warm family | cool/blue + separate `--warn` family |

Also add, all referenced by components below and previously absent:
`--accent-ink`, `--placeholder-alt`, `--warn`, `--warn-bg`, `--warn-border`,
`--space-8`, `--text-xs`, `--radius-pill`.

---

## 3. JS module & state

The largest previously-unwritten piece. Four modules, one direction of flow:

```
URL ──▶ state.read() ──▶ api.fetchImages() ──▶ render(state, data)
                ▲                                    │
                └──── state.write() ◀── user event ◀──┘
```

**State shape** — flat, serialisable, and exactly the query parameters:

```js
{ page: 1, size: "medium", grayscale: false, blur: 0, count: 10 }
```

Rules:

- **`state.js` owns URL↔state.** It parses `location.search`, applies defaults,
  and validates against the same allow-lists the server uses. It is the only
  module that touches `history`.
- **Defaults are omitted from the URL.** `?size=large` not
  `?page=1&size=large&grayscale=0&blur=0&count=10`. A clean URL is shareable.
- **A control change is `pushState`; a `popstate` is a re-render.** Back and
  forward work for free. Never `pushState` on a fetch response — only on intent.
- **`render.js` is pure-ish:** given state and data it produces DOM. It reads no
  globals and fires no fetches, so a failure state is just another render.
- **One in-flight request.** Keep an `AbortController` per fetch and abort the
  previous one; fast filter changes must not land out of order.
- **Client-side filtering is not a thing.** Filters are server parameters: they
  change which images are fetched, not which are displayed.

Fetch lifecycle, in render terms: `idle → loading → (ready | degraded | error)`.
`loading` keeps the previous grid on screen (§Loading), so there is no blank
frame between pages.

---

## 4. Components

Markup below is **plain HTML** — what JavaScript builds. Attributes JS sets at
runtime are called out per component.

### Notice banner (F2.2, F3.6)

Two sources: `?notice=` on first load, and the API's error payload thereafter.

```html
<div class="notice" role="status" data-testid="notice">
  <ul class="notice__list">
    <li>'huge' is not a valid size — showing medium.</li>
    <li>'12' is out of range for blur — showing 0.</li>
  </ul>
  <button class="notice__dismiss" type="button" aria-label="Dismiss">&times;</button>
</div>
```

*JS sets:* the whole element (absent when there is nothing to report), and the
`<li>` list.

| Cause | Message shape |
| --- | --- |
| Invalid page | `That page doesn't exist — showing page 1.` |
| Invalid parameter | `'huge' is not a valid size — showing medium.` |

Several parameters can be invalid at once — **one banner, one `<ul>`**
(`Scenario: A valid filter survives an invalid one`). A bad parameter must never
discard the good ones alongside it; surviving filters stay reflected in the
controls. `role="status"` announces without stealing focus. Informational, never
blocking; dismiss is optional and must never be the only way to continue.

### Controls

```html
<div class="controls" data-testid="controls">
  <div class="control" data-active="false">
    <label class="control__label" for="size">Size</label>
    <select class="control__field" id="size" name="size">
      <option value="small">small</option>
      <option value="medium" selected>medium</option>
      <option value="large">large</option>
    </select>
  </div>

  <div class="control control--check" data-active="false">
    <input class="control__check" type="checkbox" id="grayscale" name="grayscale">
    <label class="control__label" for="grayscale">Grayscale</label>
  </div>

  <div class="control" data-active="false">
    <label class="control__label" for="blur">Blur <output class="control__value" for="blur">0</output></label>
    <input class="control__range" type="range" id="blur" name="blur" min="0" max="10" step="1" value="0">
  </div>

  <div class="control" data-active="false">
    <label class="control__label" for="count">Per page</label>
    <select class="control__field" id="count" name="count">
      <option value="10" selected>10</option>
      <option value="20">20</option>
      <option value="50">50</option>
    </select>
  </div>

  <ul class="chips" data-testid="active-filters"></ul>
</div>
```

*JS sets:* `data-active` per control, `selected`/`checked`/`value` from state on
every render, the `<output>` text, and the chip list.

| Control | Values | Default | Requirement |
| --- | --- | --- | --- |
| Size | small / medium / large | medium | F3.1, F3.2 |
| Grayscale | on / off | off | F3.3 |
| Blur | integer 0–10 | 0 | F3.4 |
| Per page | 10 / 20 / 50 | 10 | F2.5 |

**No form, no Apply button — decided.** Under CSR there is no submit; controls
apply instantly, which is the ordinary CSR expectation and removes a click from
every filter change. The reason an Apply button was tempting is the blur field,
so:

- `select` and `checkbox` fire on `change` — one event, one fetch.
- The blur **range** fires on `input` for the `<output>` readout (free, no
  network) and requests on a **180ms debounce**, with the previous request
  aborted. Dragging the slider costs one fetch, not eleven.
- A range, not a number field: dragging is a gesture the debounce fits, and
  `min`/`max` make out-of-range values unreachable by mouse.

`min`/`max` are usability affordances only — the server still validates against
the allow-list, since a hand-edited URL bypasses the widget entirely.

**States — all three required, none is optional polish:**

- **Default** — the default value still renders as chosen. The controls have no
  empty state.
- **Active** — `data-active="true"` on a non-default value, filled `--accent`.
  Because the controls are rendered from the URL, *which* value is active must
  be visible on load.
- **Focus-visible** — the accent outline above.

Non-default filters also summarise as chips (`--accent-subtle` / `--accent-ink`),
each with a remove affordance that resets that one parameter.

**Blur and grayscale must combine** (F3.5) — they are independent parameters,
never mutually exclusive in the UI.

### Image grid

```html
<ul class="gallery" data-size="medium" data-state="ready" data-testid="gallery">
  <li class="tile">
    <a class="tile__link" href="/images/1084/?size=medium">
      <span class="tile__frame">
        <img class="tile__image" src="/img/1084/?size=medium" alt="Image 1084"
             width="400" height="400" loading="lazy" data-loaded="false">
      </span>
    </a>
    <p class="tile__caption">#1084</p>
  </li>
</ul>
```

*JS sets:* `data-size`, `data-state`, every `src`/`href`/`alt`, and
`data-loaded="true"` on the image's `load` event.

`data-size` selects the cell floor. `src` points at **Django, never picsum** —
the proxy boundary; no provider URL appears in any payload or rendered markup.
`width`/`height` reserve space so the grid never reflows; `loading="lazy"`
matters at 50 per page.

Tile links carry the current query so filters survive into the detail view and
back (`Scenario: Returning to the gallery keeps my place and my filters`).

### Loading

Two states, and **they must not be conflated**:

| State | When | Treatment |
| --- | --- | --- |
| Page fetch | Navigating, filtering, changing count | `data-state="loading"` on the grid: previous grid stays visible at `opacity: .45`, `pointer-events: none`, with a bar above it. Never blank the grid. |
| Image fetch | Per tile, after JSON arrives | `.tile__frame` holds a fixed 4:3 `--placeholder` stripe; the image fades in over `--duration` when `data-loaded="true"`. |

```html
<div class="loading" role="status" aria-live="polite" data-testid="loading" hidden>
  <span class="loading__bar"></span>
  <span class="loading__text">Loading images…</span>
</div>
```

*JS sets:* the `hidden` attribute, and `data-state` on the grid.

Because the client knows when a fetch is in flight, the indicator covers
pagination and filter changes, not only first load. Per-tile placeholders still
earn their place: each `<img>` is a separate proxy request and a 50-image page at
medium is roughly 1 MB, so reserved layout matters more than the spinner does.

### Pagination (F2.1, F2.3)

```html
<nav class="pagination" data-testid="pagination">
  <a class="pagination__link" href="?page=3">Previous</a>
  <span class="pagination__status">Page 4 of 7</span>
  <a class="pagination__link" href="?page=5">Next</a>
</nav>
```

*JS sets:* both links' `href`, the status text, and **whether each link is
rendered at all**.

**Render no element at the ends** — the Gherkin asserts absence, not a disabled
state:

```
Then there is no link to a next page
Then there is no link to a previous page
```

Real `<a href>` elements, not buttons: middle-click and copy-link keep working,
and the click handler just intercepts and calls `pushState`. Every link carries
the active size, grayscale, blur, and count (F2.3), so paging never resets the
filters.

### Detail view (F4.1, F4.4)

```html
<a class="detail__back" href="/?page=4&amp;size=small">← Back to gallery</a>
<div class="detail">
  <img class="detail__image" src="/img/1084/?size=large" alt="Image 1084">
  <dl class="params" data-testid="params">
    <dt>Identifier</dt><dd>1084</dd>
    <dt>Size</dt><dd>large</dd>
    <dt>Grayscale</dt><dd>on</dd>
    <dt>Blur</dt><dd>6</dd>
  </dl>
</div>
```

*JS sets:* the back `href` (from the gallery state it arrived with), the image
`src`, and every `<dd>`.

Side by side above 48rem, stacked below. Back link at a predictable position,
top left, preserving page and filters.

The panel reports **what was actually used**, so size reads `large` even when the
gallery was showing `small` — intentional, and this panel is where the user finds
out. A plain description list, not a decorative caption; values in `--font-mono`.

---

## 5. Failure states

Each now has markup, not just prose. None is a raw exception; none reuses the
loading placeholder.

**Failed tile** — one image timed out or returned non-success. Replaces
`.tile__frame`'s contents, keeps the aspect ratio, so one bad upstream call never
reflows the grid.

```html
<li class="tile tile--failed" data-testid="tile-failed">
  <span class="tile__frame">
    <span class="tile__fail">
      <span class="tile__fail-dot" aria-hidden="true"></span>
      Couldn't load
      <a class="tile__retry" href="/img/1084/?size=medium">Retry</a>
    </span>
  </span>
  <p class="tile__caption">#1084</p>
</li>
```

Dashed `--warn-border` on `--warn-bg` with a `--warn` dot — deliberately unlike
the striped placeholder. Retry re-requests that one image; it does not re-fetch
the page.

**Degraded** — upstream unavailable, cache warm.

```html
<div class="banner banner--warn" role="status" data-testid="degraded">
  picsum.dev isn't responding — showing cached images from 4 minutes ago.
  Filters still apply.
</div>
```

Not dismissible while the condition holds; dismissing it would hide that the
content is stale.

**Empty state** — no results, or a page past the end.

```html
<div class="empty" data-testid="empty">
  <p class="empty__title">No images to show</p>
  <p class="empty__body">This page is beyond the end of the gallery.</p>
  <a class="button button--quiet" href="?page=1">Back to page 1</a>
</div>
```

**Unreachable** — upstream unavailable, cache cold. Same card shell,
`data-testid="unreachable"`: "The image service is unreachable" / "Nothing
cached to fall back to yet. Your filters are kept in the URL." / Try again.

Plain text in a dashed box, no illustration.

### Error matrix

| Case | Treatment | API status |
| --- | --- | --- |
| Invalid parameter | Notice banner, valid filters survive | 200 |
| Invalid page | Clamp to page 1 + notice | 200 |
| One image times out | Failed tile, grid intact | 200 (tile 502) |
| Upstream down, cache warm | Degraded banner, cached grid | 200 |
| Upstream down, cache cold | Unreachable state | 503 |
| Empty result set | Empty state, link to page 1 | 200 |

Under CSR the invalid-page case is a **clamp plus `replaceState`**, not a 302 —
the client corrects the URL in place so back doesn't return to the bad page.

---

## 6. Layout

- `main` capped at `70rem`, centred, `--space-6` horizontal padding.
- Doc and panel sections are wrapping flex rows — label `flex: 0 1 200px`,
  content `flex: 1 1 420px` — so they stack on narrow screens with no media
  query.
- Controls sit **above** the grid and wrap on narrow screens. They must not push
  the first row of images off a phone screen.
- Verified at **375 / 768 / 1280**. The only breakpoint in the system is the
  480px cell-floor change.

---

## 7. Conventions

- **`data-testid` for test hooks.** Tests target these, never styling classes, so
  visual refactors don't break tests. Already the pattern in `index.html`.
- **BEM-ish naming**: `.block__element`, `.block--modifier`. Runtime state goes
  in a `data-` attribute (`data-active`, `data-size`, `data-state`,
  `data-loaded`) — never a class, so CSS never has to guess what JS meant.
- **Semantic elements first**: `<nav>` for pagination, `<dl>` for parameters,
  `<ul>` for the grid, real `<label>`s, real `<a href>`s. Accessibility comes
  from the markup, not from ARIA patches.
- **Announce async changes**: `role="status"` + `aria-live="polite"` on the
  loading indicator and banners, since the page never reloads.

## 8. Verifying a screen

1. No hardcoded colour, spacing, or size in the CSS or the JS.
2. Every state is linkable — reload the URL and get the same view.
3. Back and forward buttons work.
4. Keyboard-navigable; focus visible on every control.
5. No horizontal scroll at 320px wide.
6. Active (non-default) filter values are visible on load, from the URL alone.
7. No picsum.dev URL in the payload or the DOM.
8. A failed tile, a loading tile, and a loaded tile are three distinct things.
9. Dragging the blur slider fires one request, not eleven.

## 9. Out of scope

- Sorting, infinite scroll, lightbox.
- Client-side filtering of an already-fetched page.
- Animation beyond the image fade and the loading transition.
- Theming controls and dark mode. Light only.
- A no-JavaScript fallback — the application requires JavaScript
  ([ADR 2](adr/0002-client-side-rendering.md)).
