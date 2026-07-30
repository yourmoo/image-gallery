# UI

The visual layer, in two files that answer different questions. Read them in
order — the brief before the assets.

| File | Answers |
| --- | --- |
| [ui-notes.md](ui-notes.md) | *What must the interface do?* Control inventory, the states each control needs, layout, and the constraints from the brief |
| [design-system.md](design-system.md) | *What do I build it from?* Tokens, components, the markup each expects, and failure states |

The split is deliberate: `ui-notes.md` is the design brief and
`design-system.md` is the asset layer it is built from. A control that must
exist belongs in the first; the token or component that renders it belongs in
the second.

Neither file specifies behaviour. The Gherkin in
[tests/features/](../../tests/features/) does that, and says nothing about
appearance — it asserts *"the images are rendered in grayscale"*, never what the
grayscale control looks like. Requirement IDs (F2.x, F3.x, F4.x) are defined in
[core-features.md](../core-features.md).

## The implementation

| File | Contains |
| --- | --- |
| [`static/css/tokens.css`](../../image_gallery/static/css/tokens.css) | Every primitive value. Styles nothing. |
| [`static/css/app.css`](../../image_gallery/static/css/app.css) | Components, built only from tokens. |

## State: built

The interface these files describe is implemented. `ui-notes.md` ends with a
**Reconciliation — resolved** section recording the three items that once
blocked building: tokens a component referenced but the CSS never defined, a
palette that was a different design rather than a drifted one, and markup
written in Django template syntax for a client-rendered application
([ADR 2](../adr/0002-client-side-rendering.md)). All three were resolved on
2026-07-29, and `tokens.css` now agrees with `design-system.md`.

The record is kept because the reasoning still matters — particularly that when
the CSS on disk disagreed with `design-system.md`, the **document** turned out
to be right, twice. Treat it as the intent when the two next diverge.

Two things remain genuinely unspecified rather than merely unbuilt: the
`--image-*` tokens under custom `WxH` sizes, and the empty state and unreachable
page, neither of which the current application can reach. Both are described at
the end of `ui-notes.md`.
