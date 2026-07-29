"""Step definitions for tests/features/detail.feature.

Browser-driven, like every other step module. Steps shared with the other
feature files live in tests/e2e/conftest.py.

The detail view's defining rule is that **size and filters behave differently**
when moving from grid to detail (F4.2 vs F4.3, docs/adr/0007-detail-view-size.md):
size is presentation and is forced up to "large", while grayscale and blur are
transformations and carry over untouched. The steps below keep that distinction
visible — ``the image is rendered at size`` reads what was fetched, while
``the page shows the size`` reads the parameters panel, and a scenario asserts
both because they can disagree.

Additional data-testid hooks this module expects, beyond those listed in
test_gallery_steps.py:

    detail-image     the <img> on the detail page
    detail-failed    shown when the detail image could not be loaded
    param-id         the identifier in the parameters panel
    param-size       the size in the parameters panel
    param-grayscale  the grayscale state in the parameters panel
    param-blur       the blur value in the parameters panel
    back-to-gallery  the link returning to the grid, preserving page and filters
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import goto, query_string, tiles, wait_for_images

pytestmark = pytest.mark.e2e

scenarios("detail.feature")


# --------------------------------------------------------------------------
# Given — variations already active before the detail view is opened
# --------------------------------------------------------------------------


@given(parsers.parse('I am viewing the gallery at the "{size}" size'))
def viewing_at_size(size: str, scenario_state):
    scenario_state.setdefault("params", {})["size"] = size


@given("I have turned grayscale on")
def have_turned_grayscale_on(scenario_state):
    scenario_state.setdefault("params", {})["grayscale"] = "1"


@given(parsers.parse("I have set the blur to {blur:d}"))
def have_set_blur(blur: int, scenario_state):
    scenario_state.setdefault("params", {})["blur"] = str(blur)


# --------------------------------------------------------------------------
# When — opening a detail page
# --------------------------------------------------------------------------


@when(parsers.parse("I open the detail page for image {image_id:d}"))
def open_detail(image_id: int, scenario_state):
    goto(scenario_state, f"/images/{image_id}{query_string(scenario_state)}")
    wait_for_images(scenario_state)


@when(parsers.parse('I open the detail page for image "{image_id}"'))
def open_detail_raw(image_id: str, scenario_state):
    """Unvalidated on purpose: '0', '-3' and '999' must reach the application."""
    goto(scenario_state, f"/images/{image_id}")
    wait_for_images(scenario_state)


@when(parsers.parse('I open the detail page for image {image_id:d} with blur "{blur}"'))
def open_detail_with_blur(image_id: int, blur: str, scenario_state):
    goto(scenario_state, f"/images/{image_id}?blur={blur}")
    wait_for_images(scenario_state)


@when("I select the first image")
def select_first_image(scenario_state):
    _select_nth_image(scenario_state, 1)


@when("I select the second image")
def select_second_image(scenario_state):
    _select_nth_image(scenario_state, 2)


@when("I select the third image")
def select_third_image(scenario_state):
    _select_nth_image(scenario_state, 3)


@when("I follow the link back to the gallery")
def follow_back_link(scenario_state):
    """F4.1 — returning must restore the page and the filters.

    Clicking the real link rather than navigating by URL: the whole point is
    that the application built a link carrying that state.
    """
    page = scenario_state["page"]
    page.get_by_test_id("back-to-gallery").click()
    wait_for_images(scenario_state)


def _select_nth_image(scenario_state, position: int) -> None:
    """Click a tile in the grid, opening it from the gallery as a user would.

    Navigating straight to the detail URL would skip the link the gallery is
    required to render, so scenarios that say "I select ..." exercise the
    journey rather than the destination.
    """
    page = scenario_state["page"]
    if not page.url.startswith(scenario_state["base_url"]):
        goto(scenario_state, f"/{query_string(scenario_state)}")
        wait_for_images(scenario_state)

    tile = tiles(page).nth(position - 1)
    expect(tile).to_be_visible()
    scenario_state["selected_id"] = tile.get_attribute("data-image-id")

    # `expect_navigation` yields the response for the document request, which
    # "the response status is 200" then reads. `wait_for_load_state` returns
    # None, so assigning its result left that step asserting against nothing.
    with page.expect_navigation() as navigation:
        tile.click()
    scenario_state["response"] = navigation.value

    wait_for_images(scenario_state)


# --------------------------------------------------------------------------
# Then — the detail page itself
# --------------------------------------------------------------------------


@then(parsers.parse("I am on the detail page for image {image_id:d}"))
def on_detail_page(image_id: int, scenario_state):
    assert re.search(rf"/images/{image_id}\b", scenario_state["page"].url), (
        f"expected the detail page for image {image_id}, at {scenario_state['page'].url}"
    )


@then(parsers.parse('the image is rendered at size "{size}"'))
def image_at_named_size(size: str, scenario_state):
    """Assert on what was fetched, not on the rendered box.

    Size is a fetch-time decision (ADR 9), and CSS could scale any image to any
    box, so the request log is the only honest observation.
    """
    request = _detail_request(scenario_state)
    assert request.width is not None and request.height is not None, (
        f"upstream request carried no dimensions: {request.path}"
    )
    scenario_state["observed_dimensions"] = (request.width, request.height)


@then(parsers.parse("the image is rendered at {width:d} by {height:d} pixels"))
def image_at_custom_size(width: int, height: int, scenario_state):
    request = _detail_request(scenario_state)
    assert (request.width, request.height) == (width, height), (
        f"expected {width}x{height}, fetched {request.width}x{request.height}"
    )


@then("the image is rendered in grayscale")
def image_in_grayscale(scenario_state):
    assert _detail_request(scenario_state).grayscale, "the image was not fetched in grayscale"


@then(parsers.parse("the image is rendered with blur {blur:d}"))
def image_with_blur(blur: int, scenario_state):
    actual = _detail_request(scenario_state).blur
    assert actual == blur, f"expected blur {blur}, fetched blur {actual}"


@then("the image has no blur applied")
def image_no_blur(scenario_state):
    actual = _detail_request(scenario_state).blur
    assert actual == 0, f"expected no blur, fetched blur {actual}"


@then("the image has no filters applied")
def image_no_filters(scenario_state):
    request = _detail_request(scenario_state)
    assert not request.grayscale, "expected no grayscale"
    assert request.blur == 0, f"expected no blur, fetched blur {request.blur}"


# --------------------------------------------------------------------------
# Then — the parameters panel (F4.4)
# --------------------------------------------------------------------------


@then(parsers.parse("the page shows the image identifier {image_id:d}"))
def panel_shows_id(image_id: int, scenario_state):
    expect(scenario_state["page"].get_by_test_id("param-id")).to_contain_text(str(image_id))


@then(parsers.parse('the page shows the size "{size}"'))
def panel_shows_size(size: str, scenario_state):
    """The panel must report the size actually used.

    F4.4 is about honesty: a gallery browsed at "small" yields a detail page
    that reports "large", because that is what was rendered. Echoing the
    requested size back would be wrong.
    """
    expect(scenario_state["page"].get_by_test_id("param-size")).to_contain_text(size)


@then("the page shows that grayscale is on")
def panel_grayscale_on(scenario_state):
    _assert_panel_state(scenario_state, "param-grayscale", on=True)


@then("the page shows that grayscale is off")
def panel_grayscale_off(scenario_state):
    _assert_panel_state(scenario_state, "param-grayscale", on=False)


@then(parsers.parse("the page shows the blur value {blur:d}"))
def panel_shows_blur(blur: int, scenario_state):
    expect(scenario_state["page"].get_by_test_id("param-blur")).to_contain_text(str(blur))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _detail_request(scenario_state):
    """The upstream request the detail page caused.

    The last image request wins: opening a detail page from the grid fetches
    the grid's tiles first, and only the final one belongs to the detail view.
    """
    requests = scenario_state["upstream"].image_requests
    assert requests, "no upstream image request was made for the detail image"
    return requests[-1]


def _assert_panel_state(scenario_state, testid: str, *, on: bool) -> None:
    """Read a boolean out of the parameters panel.

    Accepts any of the obvious renderings — on/off, yes/no, true/false — so the
    assertion is about the reported state rather than a particular wording the
    Gherkin never fixed.
    """
    element = scenario_state["page"].get_by_test_id(testid)
    expect(element).to_be_visible()
    text = (element.inner_text() or "").strip().lower()

    positive = any(word in text for word in ("on", "yes", "true", "enabled"))
    negative = any(word in text for word in ("off", "no", "false", "disabled"))

    if on:
        assert positive and not negative, f"expected grayscale on, panel reads {text!r}"
    else:
        assert negative and not positive, f"expected grayscale off, panel reads {text!r}"
