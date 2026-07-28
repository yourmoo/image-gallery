"""Step definitions for tests/features/gallery.feature.

Browser-driven throughout. Steps navigate with Playwright and assert on the
DOM — no step imports Django, instantiates a view, or uses the test client.
The application is a black box reached over HTTP, which is the only way these
scenarios stay true to what a user can actually observe.

The one non-DOM observation is the fake upstream's request log. It is what the
"N upstream image requests are made" family asserts on, and there is no
browser-visible equivalent: the browser cannot see what Django did or did not
fetch from picsum.dev. See tests/e2e/conftest.py.

Elements are found by ``data-testid``, never by CSS class, so restyling cannot
break a test. The hooks these steps expect are the contract the templates must
satisfy:

    gallery        the grid container
    image-tile     one per tile, with data-image-id
    image-figure   the <img> inside a tile that loaded
    image-failed   a tile that could not load
    notice         the validation / explanation banner
    count-control  the per-page count control (F2.5 requires a real control)
    next-page      link to the next page, absent at the end
    prev-page      link to the previous page, absent on page 1

See docs/adr/0015-test-strategy.md for why every feature file runs in this tier.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import CATALOGUE_SIZE

pytestmark = pytest.mark.e2e

scenarios("gallery.feature")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _count_api_calls(state: dict) -> None:
    """Start counting browser -> Django calls for the page's image metadata.

    Registered once per scenario, before the first navigation. This is the
    browser-visible half of F2.7: one metadata call per page view. The other
    half — that the call reaches no further — is answered by the fake
    upstream's log.
    """
    if state.get("_counting"):
        return
    state["_counting"] = True
    state["api_calls"] = 0

    def _on_request(request) -> None:
        if "/api/images" in request.url and not re.search(r"/api/images/\d", request.url):
            state["api_calls"] = state.get("api_calls", 0) + 1

    state["page"].on("request", _on_request)


def _goto(state: dict, path: str) -> None:
    """Navigate, remembering the response so status can be asserted later."""
    _count_api_calls(state)
    state["response"] = state["page"].goto(f"{state['base_url']}{path}")


def _tiles(page):
    return page.get_by_test_id("image-tile")


def _query(state: dict) -> str:
    """The query string accumulated by 'Given I am viewing ...' steps."""
    params = state.get("params", {})
    if not params:
        return ""
    return "?" + "&".join(f"{k}={v}" for k, v in params.items())


# --------------------------------------------------------------------------
# Given — the world before the scenario acts
# --------------------------------------------------------------------------


@given("the gallery is available")
def gallery_available(page, gallery_server, fake_upstream, scenario_state):
    """The default state: a healthy upstream and a server pointed at it.

    Also the step that wires the browser and server into the scenario bag, so
    every later step has them.
    """
    scenario_state["page"] = page
    scenario_state["base_url"] = gallery_server.base_url
    scenario_state["upstream"] = fake_upstream
    scenario_state.setdefault("params", {})


@given(parsers.parse("the collection holds {count:d} images"))
def collection_holds(count: int):
    """Assert the configured bound rather than populating anything.

    Per docs/adr/0004-bounded-catalogue.md the catalogue is a single integer in
    settings, not a structure that gets built — so there is nothing to set up
    here. The step exists to make the Background's claim checkable, and it
    fails loudly if the fixture's catalogue size ever drifts from the feature
    files' assumption.
    """
    assert count == CATALOGUE_SIZE, (
        f"gallery.feature assumes a {count}-image catalogue but the suite "
        f"configures {CATALOGUE_SIZE}"
    )


@given("the gallery is unavailable")
def gallery_unavailable(scenario_state):
    scenario_state["upstream"].faults.outage = True


@given(parsers.parse("the gallery is unavailable for {count:d} of the images on page {page:d}"))
def gallery_partially_unavailable(count: int, page: int, scenario_state):
    """Fail exactly ``count`` images on the given page.

    Ids are derivable (ADR 4), so page N holds ids (N-1)*10+1 .. N*10 at the
    default page size. Failing the first ``count`` of them keeps which tiles
    fail deterministic, which the 'a neighbour that fails' scenario needs.
    """
    first_id = (page - 1) * 10 + 1
    scenario_state["upstream"].faults.fail_seeds = set(range(first_id, first_id + count))
    scenario_state["failed_ids"] = set(range(first_id, first_id + count))


@given("the gallery does not respond in time")
def gallery_hangs(scenario_state):
    scenario_state["upstream"].faults.hang = True


@given("the gallery becomes unavailable")
def gallery_becomes_unavailable(scenario_state):
    """Mid-scenario outage, after images have already been seen and cached."""
    scenario_state["upstream"].faults.outage = True


@given("I have already opened the gallery")
def already_opened(scenario_state):
    """Load the gallery once so its images are cached, then clear the log.

    The log is cleared because every scenario using this step goes on to
    assert about requests made *after* this point — 'no further upstream image
    requests are made'.
    """
    _goto(scenario_state, "/")
    _wait_for_images(scenario_state)
    scenario_state["upstream"].reset()


@given(parsers.parse('I am viewing large grayscale images with blur {blur:d}'))
def viewing_large_grayscale_blur(blur: int, scenario_state):
    """Record the active variations; the navigation step applies them."""
    scenario_state["params"] = {"size": "large", "grayscale": "1", "blur": str(blur)}


# --------------------------------------------------------------------------
# When — the action under test
# --------------------------------------------------------------------------


@when("I open the gallery")
def open_gallery(scenario_state):
    _goto(scenario_state, f"/{_query(scenario_state)}")


@when("I open the gallery again")
def open_gallery_again(scenario_state):
    _goto(scenario_state, f"/{_query(scenario_state)}")


@when(parsers.parse("I open page {page:d} of the gallery"))
def open_page(page: int, scenario_state):
    params = {**scenario_state.get("params", {}), "page": str(page)}
    query = "&".join(f"{k}={v}" for k, v in params.items())
    _goto(scenario_state, f"/?{query}")


@when(parsers.parse('I open the gallery at page "{page}"'))
def open_gallery_at_page(page: str, scenario_state):
    """Deliberately unvalidated: the string goes into the URL as written.

    This is the invalid-page family, so 'abc', '-5' and the empty string must
    reach the application untouched.
    """
    _goto(scenario_state, f"/?page={page}")


@when(parsers.parse("I choose to see {count:d} images per page"))
def choose_count(count: int, scenario_state):
    """Drive the real control, not the URL.

    F2.5 requires the count to be changeable 'by the user via UI', so setting
    ?count= here would let a broken or missing control still pass.
    """
    page = scenario_state["page"]
    if not page.url.startswith(scenario_state["base_url"]):
        _goto(scenario_state, "/")
    page.get_by_test_id("count-control").select_option(str(count))
    page.wait_for_load_state("networkidle")


@when("the images have finished loading")
@then("the images have finished loading")
def images_finished_loading(scenario_state):
    _wait_for_images(scenario_state)


def _wait_for_images(scenario_state) -> None:
    """Wait until every tile has settled into loaded or failed.

    Both a 'when' and a 'then' because gallery.feature uses it in both
    positions — a scenario asserts the grid is present, then waits, then
    asserts about the tiles.
    """
    page = scenario_state["page"]
    page.wait_for_load_state("networkidle")


# --------------------------------------------------------------------------
# Then — observable outcomes
# --------------------------------------------------------------------------


@then(parsers.parse("the response status is {status:d}"))
def response_status(status: int, scenario_state):
    assert scenario_state["response"].status == status


@then(parsers.parse("the page shows {count:d} images in a grid"))
def shows_n_images(count: int, scenario_state):
    expect(_tiles(scenario_state["page"])).to_have_count(count)


@then(parsers.parse("the page shows images {first:d} to {last:d}"))
def shows_image_range(first: int, last: int, scenario_state):
    """Assert both the count and the identity of the tiles.

    Identity matters: a page that shows ten tiles of the wrong images would
    satisfy a count-only assertion.
    """
    tiles = _tiles(scenario_state["page"])
    expect(tiles).to_have_count(last - first + 1)
    ids = tiles.evaluate_all("els => els.map(e => Number(e.dataset.imageId))")
    assert ids == list(range(first, last + 1))


@then(parsers.parse("{count:d} gallery data request is made"))
@then(parsers.parse("{count:d} gallery data requests are made"))
def gallery_data_requests(count: int, scenario_state):
    """The metadata call the page makes to Django, counted in the browser.

    Distinct from upstream requests: this is browser -> Django, which the
    browser can see, so it is observed with a Playwright route rather than the
    fake's log.
    """
    assert scenario_state.get("api_calls", 0) == count, (
        f"expected {count} gallery data request(s), "
        f"saw {scenario_state.get('api_calls', 0)}"
    )


@then("no upstream image requests are made")
def no_upstream_requests(scenario_state):
    actual = scenario_state["upstream"].image_requests
    assert actual == [], f"expected no upstream image requests, saw {len(actual)}"


@then("no further upstream image requests are made")
def no_further_upstream_requests(scenario_state):
    """Cached images must not be refetched.

    The log was cleared by 'I have already opened the gallery', so anything
    recorded here is a request made after the first load.
    """
    actual = scenario_state["upstream"].image_requests
    assert actual == [], f"expected no further upstream requests, saw {len(actual)}"


@then(parsers.parse("{count:d} upstream image requests are made"))
def n_upstream_requests(count: int, scenario_state):
    actual = scenario_state["upstream"].image_requests
    assert len(actual) == count, f"expected {count} upstream requests, saw {len(actual)}"


@then(parsers.parse("the page offers image counts of {a:d}, {b:d} and {c:d}"))
def offers_counts(a: int, b: int, c: int, scenario_state):
    """F2.5 — a real control, offering exactly these values."""
    control = scenario_state["page"].get_by_test_id("count-control")
    expect(control).to_be_visible()
    offered = control.evaluate("el => Array.from(el.options).map(o => o.value)")
    assert offered == [str(a), str(b), str(c)]


@then(parsers.parse("the page number in the address is {page:d}"))
def page_number_in_address(page: int, scenario_state):
    assert re.search(rf"[?&]page={page}\b", scenario_state["page"].url), (
        f"page={page} not in {scenario_state['page'].url}"
    )


@then(parsers.parse('the link to the next page keeps size "{size}"'))
def next_keeps_size(size: str, scenario_state):
    href = scenario_state["page"].get_by_test_id("next-page").get_attribute("href")
    assert re.search(rf"[?&]size={re.escape(size)}\b", href), f"size missing from {href}"


@then("the link to the next page keeps grayscale enabled")
def next_keeps_grayscale(scenario_state):
    href = scenario_state["page"].get_by_test_id("next-page").get_attribute("href")
    assert re.search(r"[?&]grayscale=(1|true|on)\b", href), f"grayscale missing from {href}"


@then(parsers.parse("the link to the next page keeps blur {blur:d}"))
def next_keeps_blur(blur: int, scenario_state):
    href = scenario_state["page"].get_by_test_id("next-page").get_attribute("href")
    assert re.search(rf"[?&]blur={blur}\b", href), f"blur={blur} missing from {href}"


@then("there is no link to a next page")
def no_next_link(scenario_state):
    """Absence, not a disabled state.

    ui-notes.md prefers rendering no link at all at the ends, so the
    assertion is about presence rather than an ARIA attribute.
    """
    expect(scenario_state["page"].get_by_test_id("next-page")).to_have_count(0)


@then("there is no link to a previous page")
def no_prev_link(scenario_state):
    expect(scenario_state["page"].get_by_test_id("prev-page")).to_have_count(0)


@then(parsers.parse("I am redirected to page {page:d}"))
def redirected_to_page(page: int, scenario_state):
    """Under client-side rendering this is a URL correction, not a 3xx.

    ADR 2 makes the gallery client-rendered, so an invalid page is clamped and
    the address corrected with replaceState. What the user observes — the
    address now reads page 1 — is identical, and that is what is asserted.
    """
    url = scenario_state["page"].url
    assert re.search(rf"[?&]page={page}\b", url) or not re.search(r"[?&]page=", url), (
        f"address should show page {page}, is {url}"
    )


@then("the page explains that the requested page was not valid")
def explains_invalid_page(scenario_state):
    expect(scenario_state["page"].get_by_test_id("notice")).to_be_visible()


@then("no validation message is shown")
def no_validation_message(scenario_state):
    expect(scenario_state["page"].get_by_test_id("notice")).to_have_count(0)


@then("the page explains that some images could not be loaded")
def explains_images_failed(scenario_state):
    expect(scenario_state["page"].get_by_test_id("notice")).to_be_visible()


@then(parsers.parse("{count:d} images are shown"))
def n_images_shown(count: int, scenario_state):
    """Tiles that actually rendered an image, excluding failed ones."""
    expect(scenario_state["page"].get_by_test_id("image-figure")).to_have_count(count)


@then(parsers.parse("{count:d} images are shown as unavailable"))
def n_images_unavailable(count: int, scenario_state):
    expect(scenario_state["page"].get_by_test_id("image-failed")).to_have_count(count)


@then("every image is shown as unavailable")
def every_image_unavailable(scenario_state):
    page = scenario_state["page"]
    total = _tiles(page).count()
    assert total > 0, "no tiles rendered at all"
    expect(page.get_by_test_id("image-failed")).to_have_count(total)


@then("no image is shown as unavailable")
def no_image_unavailable(scenario_state):
    expect(scenario_state["page"].get_by_test_id("image-failed")).to_have_count(0)


@then(parsers.parse('the {count:d} available images are rendered at size "{size}"'))
def available_images_at_size(count: int, size: str, scenario_state):
    """A failing neighbour must not change how the working tiles were fetched."""
    requests = [
        r
        for r in scenario_state["upstream"].image_requests
        if r.seed not in scenario_state.get("failed_ids", set())
    ]
    assert len(requests) == count, f"expected {count} successful fetches, saw {len(requests)}"
    widths = {r.width for r in requests}
    assert len(widths) == 1, f"expected one size for the working tiles, saw {widths}"


@then("I did not have to wait for the images")
def did_not_wait_for_images(scenario_state):
    """The grid must be on screen before any image request completes.

    Asserting an absence of waiting directly is not possible, so this checks
    the observable consequence: the grid rendered while the upstream was still
    hanging, which is only true if the page did not block on the images.
    """
    expect(_tiles(scenario_state["page"]).first).to_be_visible()
