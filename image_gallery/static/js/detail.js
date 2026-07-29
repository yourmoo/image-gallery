/*
 * The detail page's parameters panel, made instant.
 *
 * The panel is a real `<form>` with a submit button, because this page is
 * server-rendered and has to work with no script at all. This file is the
 * progressive enhancement: when it runs, changing a control submits the form
 * immediately and the button becomes redundant, so the detail page behaves
 * like the gallery rather than being the one screen that needs a button
 * (docs/ui/ui-notes.md — controls apply instantly, no Apply).
 *
 * This file is the **pure half** — which controls self-apply, and on what
 * event. It touches no DOM, so it can be unit-tested without a browser
 * (tests/unit/js/detail.test.js). The wiring lives in detail-panel.js, which
 * imports it; that split is the same one derive.js and gallery.js use, and it
 * exists because a module that reads `document` at import time cannot be
 * loaded by a test runner at all.
 */

/* Whether a control should apply on its own, or wait for the button.
 *
 * Every input the panel offers does: a select, a checkbox, a range, and a text
 * field all represent a completed choice by the time they fire `change`.
 *
 * The text field was excluded at first, on the worry that it would navigate on
 * every keystroke. That is `input`, not `change` — a text field fires `change`
 * only when it loses focus or Enter is pressed, both of which mean the user
 * has finished typing. Excluding it left the custom-size field inert, since
 * the Apply button it was meant to fall back to had already been hidden.
 *
 * The button and this list are still separate concerns: the button exists for
 * a browser with no script at all, not as a fallback for particular controls.
 */
export function appliesImmediately(type) {
  return (
    type === "select-one" ||
    type === "checkbox" ||
    type === "range" ||
    type === "text"
  );
}

/* The event that means "the user has finished choosing".
 *
 * `change` throughout, including for the range. A range also fires `input`
 * continuously while dragging, and submitting on that would mean eleven
 * navigations for one drag of the blur slider. `change` fires once, when the
 * drag ends — the same reasoning the gallery's blur control uses, and why
 * neither needs a debounce timer.
 */
export function submitEvent(type) {
  return appliesImmediately(type) ? "change" : null;
}
