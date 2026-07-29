"""Step definitions for tests/features/variations.feature.

Browser-driven, like every other step module: navigate with Playwright, assert
on the DOM. Steps shared with gallery.feature and detail.feature — navigation,
status, notices, the grid assertions — live in tests/e2e/conftest.py so
pytest-bdd resolves them across all three feature files rather than each module
redefining them.

How a variation is asserted depends on what the scenario is really claiming:

* **What the user sees** — grayscale and blur are CSS filters on the rendered
  tile, so those steps read the computed style from the browser.
* **What the application asked for** — size is a fetch-time decision, and the
  honest observation is the width and height Django requested from upstream,
  read from the fake's request log.

Mixing the two would let a page that renders correctly but fetches wastefully
pass, or vice versa. See docs/adr/0009-url-vocabularies.md for the size
vocabulary and docs/core-features.md for F3.1-F3.6.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect
from pytest_bdd import parsers, scenarios, then, when

from conftest import empty_image_cache, goto, query_string, tiles, wait_for_images

pytestmark = pytest.mark.e2e

scenarios("variations.feature")


# --------------------------------------------------------------------------
# When — changing how images are rendered
# --------------------------------------------------------------------------


def _open_gallery_for_controls(scenario_state) -> None:
    """Land on the gallery, then forget everything that loading it did.

    Driving a control needs the page open first, and opening it fetches a
    page's worth of images at the *current* settings. Those requests are not
    evidence about the setting under test — without clearing them,
    `I choose the "large" size` is asserted against ten medium requests from
    the navigation plus ten large ones from the change.

    Both the log **and the image cache** are emptied, because clearing only the
    log is not enough. A tile the first navigation cached is served without the
    fake being consulted at all, so choosing a value that was already cached —
    or choosing the default, which does not navigate — would leave the log
    empty and the assertion with nothing to read.
    """
    page = scenario_state["page"]
    if not page.url.startswith(scenario_state["base_url"]):
        goto(scenario_state, "/")
        wait_for_images(scenario_state)

    empty_image_cache()
    scenario_state["upstream"].reset()


@when(parsers.parse('I choose the "{size}" size'))
def choose_size(size: str, scenario_state):
    """Drive the real control.

    F3.1 offers named sizes through the UI, so setting ?size= here would let a
    missing or broken control still pass.
    """
    _open_gallery_for_controls(scenario_state)
    scenario_state["page"].get_by_test_id("size-control").select_option(size)
    wait_for_images(scenario_state)


@when("I turn grayscale on")
def turn_grayscale_on(scenario_state):
    _open_gallery_for_controls(scenario_state)
    scenario_state["page"].get_by_test_id("grayscale-control").check()
    wait_for_images(scenario_state)


@when(parsers.parse("I set the blur to {blur:d}"))
def set_blur(blur: int, scenario_state):
    _open_gallery_for_controls(scenario_state)
    blur_control = scenario_state["page"].get_by_test_id("blur-control")
    blur_control.fill(str(blur))
    blur_control.dispatch_event("change")
    wait_for_images(scenario_state)


@when(parsers.parse('I open the gallery with blur "{blur}"'))
def open_with_blur(blur: str, scenario_state):
    goto(scenario_state, f"/?blur={blur}")
    wait_for_images(scenario_state)


@when(parsers.parse('I open the gallery with a count of "{count}"'))
def open_with_count(count: str, scenario_state):
    goto(scenario_state, f"/?count={count}")
    wait_for_images(scenario_state)


@when(parsers.parse('I open the gallery with size "{size}" and blur {blur:d}'))
def open_with_size_and_blur(size: str, blur: int, scenario_state):
    """One bad parameter must not discard the good one alongside it."""
    goto(scenario_state, f"/?size={size}&blur={blur}")
    wait_for_images(scenario_state)


# --------------------------------------------------------------------------
# Then — how the images came out
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
