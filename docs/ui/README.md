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

## State: not yet build-ready

`ui-notes.md` ends with a **Handover** section listing what must be resolved
before templates are written. One item is settled — the interface is light only,
dark mode is removed — and the rest are open. The largest is that
`design-system.md` and `tokens.css` currently describe **different designs**,
with a table of the diverging values and a decision recorded on which to take as
intent.

The component blocks in `design-system.md` are written in Django template
syntax, but the application is client-rendered
([ADR 2](../adr/0002-client-side-rendering.md)) — that mismatch is Handover
item 3 and is not yet resolved.

Read that section before building anything from these files.
