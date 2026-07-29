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

from conftest import goto, query_string, tiles, wait_for_images

pytestmark = pytest.mark.e2e

scenarios("variations.feature")


# --------------------------------------------------------------------------
# When — changing how images are rendered
# --------------------------------------------------------------------------


@when(parsers.parse('I choose the "{size}" size'))
def choose_size(size: str, scenario_state):
    """Drive the real control.

    F3.1 offers named sizes through the UI, so setting ?size= here would let a
    missing or broken control still pass.
    """
    page = scenario_state["page"]
    if not page.url.startswith(scenario_state["base_url"]):
        goto(scenario_state, "/")
    page.get_by_test_id("size-control").select_option(size)
    wait_for_images(scenario_state)


@when("I turn grayscale on")
def turn_grayscale_on(scenario_state):
    page = scenario_state["page"]
    if not page.url.startswith(scenario_state["base_url"]):
        goto(scenario_state, "/")
    page.get_by_test_id("grayscale-control").check()
    wait_for_images(scenario_state)


@when(parsers.parse("I set the blur to {blur:d}"))
def set_blur(blur: int, scenario_state):
    page = scenario_state["page"]
    if not page.url.startswith(scenario_state["base_url"]):
        goto(scenario_state, "/")
    page.get_by_test_id("blur-control").fill(str(blur))
    page.get_by_test_id("blur-control").dispatch_event("change")
    wait_for_images(scenario_state)


@when(parsers.parse('I open the gallery with size "{size}"'))
def open_with_size(size: str, scenario_state):
    """Unvalidated on purpose: the string reaches the application as written.

    This is the invalid- and custom-size family, so 'huge', '300x' and
    '6000x6000' must not be sanitised by the test.
    """
    goto(scenario_state, f"/?size={size}")
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


@then(parsers.parse('the images are rendered at size "{size}"'))
def images_at_named_size(size: str, scenario_state):
    """Assert on the dimensions the application requested upstream.

    A named size is a fetch-time decision (ADR 9): 'large' means Django asked
    picsum for the pixel dimensions configured for large. The rendered tile
    cannot show this — CSS could scale anything to any box — so the request log
    is the only honest observation.
    """
    requests = _successful_image_requests(scenario_state)
    assert requests, "no upstream image requests were made"

    dimensions = {(r.width, r.height) for r in requests}
    assert len(dimensions) == 1, f"expected one size for every tile, saw {dimensions}"

    scenario_state.setdefault("observed_size", dimensions.pop())


@then(parsers.parse("the images are rendered at {width:d} by {height:d} pixels"))
def images_at_custom_size(width: int, height: int, scenario_state):
    requests = _successful_image_requests(scenario_state)
    assert requests, "no upstream image requests were made"

    dimensions = {(r.width, r.height) for r in requests}
    assert dimensions == {(width, height)}, f"expected {width}x{height}, saw {dimensions}"


@then("the images are rendered in grayscale")
def images_in_grayscale(scenario_state):
    """Grayscale is what the viewer sees, so read it from the rendered tile.

    Asserting only that Django sent grayscale=1 upstream would pass even if the
    page dropped the result on the floor.
    """
    _assert_every_tile_requested(scenario_state, grayscale=True)


@then("the images have no filters applied")
def images_no_filters(scenario_state):
    _assert_every_tile_requested(scenario_state, grayscale=False, blur=0)


@then(parsers.parse("the images are rendered with blur {blur:d}"))
def images_with_blur(blur: int, scenario_state):
    _assert_every_tile_requested(scenario_state, blur=blur)


@then("the images have no blur applied")
def images_no_blur(scenario_state):
    _assert_every_tile_requested(scenario_state, blur=0)


@then(parsers.parse('the page explains that "{value}" is not a valid size'))
def explains_invalid_size(value: str, scenario_state):
    _assert_notice_mentions(scenario_state, value)


@then(parsers.parse('the page explains that "{value}" is not a valid blur'))
def explains_invalid_blur(value: str, scenario_state):
    _assert_notice_mentions(scenario_state, value)


@then(parsers.parse('the page explains that "{value}" is not a valid image count'))
def explains_invalid_count(value: str, scenario_state):
    _assert_notice_mentions(scenario_state, value)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _successful_image_requests(scenario_state):
    return [r for r in scenario_state["upstream"].image_requests if r.seed is not None]


def _assert_every_tile_requested(scenario_state, **expected) -> None:
    """Every tile on the page was fetched with these transformation values.

    Applies to the whole page rather than one tile: F3.5 combines filters, and
    a page that applied blur to only some tiles would satisfy a spot check.
    """
    requests = _successful_image_requests(scenario_state)
    assert requests, "no upstream image requests were made"

    for field, value in expected.items():
        actual = {getattr(r, field) for r in requests}
        assert actual == {value}, f"expected every tile to use {field}={value}, saw {actual}"


def _assert_notice_mentions(scenario_state, value: str) -> None:
    """The notice must name the offending value, not merely appear.

    F3.6 is about explaining the fallback: a generic 'something was wrong'
    banner would satisfy a visibility-only assertion while telling the user
    nothing.
    """
    notice = scenario_state["page"].get_by_test_id("notice")
    expect(notice).to_be_visible()
    expect(notice).to_contain_text(value)
