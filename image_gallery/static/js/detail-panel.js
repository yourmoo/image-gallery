/*
 * Wiring for the detail page's parameters panel.
 *
 * The panel is a real `<form>` with a submit button, because this page is
 * server-rendered and has to work with no script at all. This file is the
 * progressive enhancement: when it runs, changing a control submits the form
 * immediately and the button becomes redundant, so the detail page behaves
 * like the gallery rather than being the one screen that needs a button
 * (docs/ui/ui-notes.md — controls apply instantly, no Apply).
 *
 * DOM only. Every decision it makes comes from detail.js, which is pure and
 * unit-tested; what is left here needs a document and is covered by the
 * browser tier.
 */

import { submitEvent } from "./detail.js";

const form = document.querySelector('[data-testid="params"]');

if (form) {
  for (const control of form.elements) {
    const event = submitEvent(control.type);
    if (event) {
      control.addEventListener(event, () => form.submit());
    }
  }

  /* The readout beside the blur slider tracks the drag, so the number moves
   * with the thumb even though nothing is submitted until release. */
  const blur = form.querySelector('[data-testid="blur-control"]');
  const readout = blur && blur.parentElement.querySelector(".params__value");
  if (blur && readout) {
    blur.addEventListener("input", () => {
      readout.textContent = blur.value;
    });
  }

  /* Redundant once the controls apply themselves, but kept in the DOM for
   * anyone without script — hidden rather than removed. */
  const apply = form.querySelector('[data-testid="apply"]');
  if (apply) apply.hidden = true;
}
