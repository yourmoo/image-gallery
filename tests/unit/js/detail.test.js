/*
 * The detail page's control logic.
 *
 * Its panel is a real form with a submit button, because the page is
 * server-rendered and must work without JavaScript. When script *is* available
 * the form applies on change instead, so the detail page behaves like the
 * gallery rather than being the one screen that needs a button
 * (docs/adr/0007-detail-view-size.md § Amendment).
 *
 * Only the decision is tested here: which controls should apply immediately,
 * and whether the button is still needed. Submitting is DOM work and belongs
 * to the browser tier.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { appliesImmediately, submitEvent } from "../../../image_gallery/static/js/detail.js";

describe("appliesImmediately", () => {
  it("applies a select as soon as the choice is made", () => {
    // One event, one navigation — the same rule the gallery's size and count
    // controls follow.
    assert.equal(appliesImmediately("select-one"), true);
  });

  it("applies a checkbox as soon as it is toggled", () => {
    assert.equal(appliesImmediately("checkbox"), true);
  });

  it("applies a range too, but on a different event", () => {
    assert.equal(appliesImmediately("range"), true);
  });

  it("applies a text field too, since `change` means committed", () => {
    // The worry was navigating per keystroke, but that is `input`, not
    // `change` — a text field fires `change` when it loses focus or Enter is
    // pressed, both of which mean the user has finished typing. Excluding it
    // left the custom-size field inert unless the Apply button was clicked,
    // which script had already hidden.
    assert.equal(appliesImmediately("text"), true);
  });

  it("leaves the submit button alone", () => {
    assert.equal(appliesImmediately("submit"), false);
    assert.equal(appliesImmediately("hidden"), false);
  });
});

describe("submitEvent", () => {
  it("uses change for a select, so one choice is one navigation", () => {
    assert.equal(submitEvent("select-one"), "change");
  });

  it("uses change for a checkbox", () => {
    assert.equal(submitEvent("checkbox"), "change");
  });

  it("uses change for a range, not input", () => {
    // `input` fires continuously while dragging; `change` fires once when the
    // drag ends. Dragging the blur slider is one request, not eleven — the
    // same reasoning the gallery's blur control uses, and why neither needs a
    // debounce timer.
    assert.equal(submitEvent("range"), "change");
  });

  it("uses change for a text field, which fires on commit not on keystroke", () => {
    assert.equal(submitEvent("text"), "change");
  });

  it("gives nothing for a control that does not self-apply", () => {
    assert.equal(submitEvent("submit"), null);
  });
});
