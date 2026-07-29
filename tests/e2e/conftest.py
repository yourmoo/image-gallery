"""Fixtures for the browser-driven BDD suite.

The suite runs against the stack in compose.e2e.yaml: the **production image**
serving through real gunicorn, pointed at a fake picsum.dev in its own
container. Running the shipped image matters — each gunicorn worker holds its
own LocMemCache, and a single-process harness cannot observe that at all.

    docker compose -f compose.e2e.yaml up -d --build
    pytest -c tests/pytest.ini -m e2e

Because the fake runs in a different process, faults and the request log are
driven over HTTP through its ``/_control`` API. That surface exists only on the
fake, which is test infrastructure; the application image carries no test
scaffolding, as the project's SOLID and 12-factor guardrails require.

Nothing here imports Django. Steps drive the browser and assert on the DOM; the
only non-browser observation is the fake's request log, which is the sole way
to answer "no upstream image requests are made" — the browser cannot see what
Django did or did not fetch.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect
from pytest_bdd import given, parsers, then, when

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "compose.e2e.yaml"

# Where compose.e2e.yaml publishes the two services.
WEB_BASE_URL = os.environ.get("E2E_WEB_URL", "http://127.0.0.1:8081")
FAKE_CONTROL_URL = os.environ.get("E2E_FAKE_URL", "http://127.0.0.1:8091")

# The catalogue every feature file's Background declares. Must match
# GALLERY_CATALOGUE_SIZE in compose.e2e.yaml.
CATALOGUE_SIZE = 100

# Scenarios whose outcome depends on the image cache being empty. Everything
# else shares the running stack; these restart `web` first, so images cached by
# an earlier scenario cannot make them pass for the wrong reason.
#
# Matched against the generated test name, which pytest-bdd derives from the
# scenario title. A rename would silently drop an entry here and let the
# scenario run warm — tests/unit/python/test_bdd_harness.py fails the build if that
# happens.
COLD_CACHE_SCENARIOS = {
    # Counts upstream calls, so a cached image would make it fail for the right
    # reason at the wrong time: the calls did happen, on an earlier scenario.
    "test_a_page_is_composed_from_one_upstream_call_per_image",
    # The partial-failure pair. An injected fault only has an effect on an
    # image the application must actually fetch — a cached one is served
    # without consulting the fake at all, so the tile that was supposed to fail
    # succeeds instead.
    "test_a_page_still_renders_when_some_images_are_unavailable",
    "test_a_working_image_is_unaffected_by_a_neighbour_that_fails",
    "test_images_never_seen_before_are_shown_as_unavailable",
    "test_a_slow_gallery_does_not_hold_the_page_open_indefinitely",
    "test_the_grid_appears_before_the_images_do",
    # The variation scenarios assert on the dimensions and filters the
    # application *requested upstream*, which is the only honest evidence a
    # transformation was applied — the fake returns the same pixel either way.
    # A cached tile is served without consulting the fake at all, so a warm
    # cache leaves nothing to assert on. Most acute for the default cases
    # (`medium`, `blur=0`), where the page under test is the one already
    # cached by the scenario's own first navigation.
    "test_images_are_shown_at_the_default_size_when_i_ask_for_nothing",
    "test_choosing_a_named_size",
    "test_asking_for_a_custom_size",
    "test_viewing_the_collection_in_grayscale",
    "test_blurring_the_images",
    "test_combining_grayscale_and_blur",
    "test_size_and_filters_apply_together",
    # The rejection scenarios, for the same reason once removed. Each opens
    # with a bad parameter, is corrected to the defaults, and then asserts what
    # the *defaults* were fetched at — and the default page is the one every
    # other scenario has already cached.
    "test_a_custom_size_outside_the_allowed_bounds_is_rejected",
    "test_a_custom_size_is_kept_when_i_move_between_pages",
    "test_an_invalid_size_falls_back_to_the_default_and_says_so",
    "test_a_blur_outside_the_range_falls_back_to_none_and_says_so",
    "test_an_invalid_count_falls_back_to_the_default_and_says_so",
    "test_a_valid_filter_survives_an_invalid_one",
    "test_active_variations_are_kept_when_i_move_between_pages",
    # The detail scenarios, again for the same reason: they assert on the
    # dimensions the detail image was *fetched* at, and the gallery scenarios
    # have already cached most of the catalogue at most of the sizes.
    "test_opening_an_image_from_the_gallery",
    "test_the_detail_view_shows_a_larger_image",
    "test_the_detail_view_is_large_whatever_size_the_gallery_used",
    "test_a_custom_size_larger_than_large_is_kept_on_the_detail_page",
    "test_a_custom_size_smaller_than_large_is_replaced_by_large",
    "test_active_filters_carry_over_to_the_detail_view",
    "test_an_unfiltered_gallery_gives_an_unfiltered_detail_view",
    "test_the_detail_page_lists_the_parameters_used",
    "test_the_parameters_panel_reports_defaults_when_nothing_is_chosen",
    "test_returning_to_the_gallery_keeps_my_place_and_my_filters",
    "test_an_invalid_filter_on_the_detail_page_falls_back_and_says_so",
}


@dataclass
class UpstreamRequest:
    """One request the application made to the fake."""

    path: str
    width: int | None
    height: int | None
    seed: int | None
    grayscale: bool
    blur: int


class Faults:
    """Fault settings, applied to the fake as they are assigned.

    Deliberately mimics a plain mutable object so step definitions read
    naturally (``upstream.faults.outage = True``) while each assignment is
    pushed to the fake over HTTP.
    """

    def __init__(self, client: "FakeUpstream") -> None:
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_values", {"outage": False, "hang": False, "fail_seeds": []})

    def __setattr__(self, name: str, value) -> None:
        if name not in ("outage", "hang", "fail_seeds"):
            raise AttributeError(f"unknown fault: {name}")
        values = object.__getattribute__(self, "_values")
        values[name] = sorted(value) if name == "fail_seeds" else value
        object.__getattribute__(self, "_client").push_faults(values)

    def __getattr__(self, name: str):
        values = object.__getattribute__(self, "_values")
        if name in values:
            return values[name]
        raise AttributeError(name)

    def as_dict(self) -> dict:
        return dict(object.__getattribute__(self, "_values"))


class FakeUpstream:
    """HTTP client for the fake picsum.dev's control API.

    Presents the same interface the step definitions used when the fake ran
    in-process — ``faults``, ``image_requests``, ``reset()`` — so moving it
    into a container changed no step.
    """

    def __init__(self, control_url: str) -> None:
        self.control_url = control_url.rstrip("/")
        self.faults = Faults(self)

    # -- control -------------------------------------------------------

    def push_faults(self, values: dict) -> None:
        self._post("/_control/faults", values)

    def reset(self) -> None:
        """Clear the request log and every injected fault.

        Called between scenarios. Without it the request counts leak from one
        scenario into the next and the upstream-call assertions stop meaning
        anything.
        """
        self._post("/_control/reset", {})
        object.__setattr__(
            self.faults, "_values", {"outage": False, "hang": False, "fail_seeds": []}
        )

    # -- observation ---------------------------------------------------

    @property
    def requests(self) -> list[UpstreamRequest]:
        """Every request since the last reset, in order."""
        raw = self._get("/_control/requests")
        return [UpstreamRequest(**item) for item in raw]

    @property
    def image_requests(self) -> list[UpstreamRequest]:
        """Requests that asked for an image.

        Distinguished from anything else that might reach the upstream, so
        "no upstream image requests are made" stays true to its wording.
        """
        return [r for r in self.requests if r.seed is not None]

    # -- transport -----------------------------------------------------

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{self.control_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read() or b"{}")

    def _get(self, path: str):
        with urllib.request.urlopen(f"{self.control_url}{path}", timeout=10) as response:
            return json.loads(response.read() or b"[]")


def _compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


def _wait_for(url: str, timeout: float = 90.0, what: str = "service") -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
        time.sleep(0.3)
    raise RuntimeError(f"{what} at {url} never became healthy: {last}")


def empty_image_cache() -> None:
    """Delete every cached image from the running `web` service.

    The cache is a directory in shared memory, so emptying it is a file
    deletion rather than a container restart — faster, and it disturbs nothing
    else about the service. Done from outside the application: a test-only
    flush endpoint would put scaffolding into production code, which the
    project's guardrails rule out.

    Exposed as a function as well as a fixture because a step sometimes needs
    to empty it *mid-scenario* — after navigating to the gallery but before
    driving a control — so that what the control does is the only thing the
    upstream log describes.
    """
    _compose(
        "exec", "-T", "web",
        "sh", "-c", "rm -rf /dev/shm/gallery-cache/* 2>/dev/null || true",
        check=False,
    )


def _stack_is_up() -> bool:
    try:
        with urllib.request.urlopen(f"{WEB_BASE_URL}/healthz", timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


@pytest.fixture(scope="session")
def e2e_stack():
    """The compose stack the suite runs against.

    If it is already up — the usual case in development, and how CI keeps the
    build step separate — it is used as-is and left running. Otherwise it is
    started here and torn down afterwards, so a bare ``pytest -m e2e`` works
    without a separate command.
    """
    if _stack_is_up():
        yield
        return

    if not COMPOSE_FILE.exists():
        pytest.skip(f"{COMPOSE_FILE.name} not found")

    _compose("up", "-d", "--build")
    try:
        _wait_for(f"{FAKE_CONTROL_URL}/_control/health", what="fake upstream")
        _wait_for(f"{WEB_BASE_URL}/healthz", what="web")
        yield
    finally:
        _compose("down", "-v", check=False)


@pytest.fixture(scope="session")
def fake_upstream(e2e_stack) -> FakeUpstream:
    """Control client for the fake picsum.dev."""
    return FakeUpstream(FAKE_CONTROL_URL)


@dataclass
class GalleryServer:
    """Where the application under test is reachable."""

    base_url: str


@pytest.fixture(scope="session")
def _session_server(e2e_stack) -> GalleryServer:
    return GalleryServer(WEB_BASE_URL)


def _wants_cold_cache(request) -> bool:
    """Whether the running scenario needs a guaranteed-empty cache.

    Decided from the test's own name at request time. Marker- and
    fixturename-based approaches do not work here: pytest-bdd generates its
    items too late for a collection hook to influence their fixture closure.
    """
    name = getattr(request.node, "originalname", None) or request.node.name
    return name in COLD_CACHE_SCENARIOS


@pytest.fixture
def cold_cache(e2e_stack) -> GalleryServer:
    """A `web` service with a guaranteed-empty image cache.

    The cache is a directory in shared memory, so emptying it is a file
    deletion rather than a container restart -- faster, and it clears the cache
    without disturbing anything else about the running service.

    Still done from outside the application: a test-only flush endpoint would
    put scaffolding into production code, which the project's guardrails rule
    out.
    """
    empty_image_cache()
    return GalleryServer(WEB_BASE_URL)


@pytest.fixture
def gallery_server(_session_server, request) -> GalleryServer:
    """The server a scenario should drive.

    Normally the running stack. A scenario listed in COLD_CACHE_SCENARIOS gets
    a restarted `web` first.
    """
    if _wants_cold_cache(request):
        return request.getfixturevalue("cold_cache")
    return _session_server


@pytest.fixture(autouse=True)
def _reset_upstream(fake_upstream):
    """Clear the request log and injected faults before every scenario.

    Autouse: a scenario that forgot this would silently inherit the previous
    one's request counts, and the upstream-call assertions would stop meaning
    anything.
    """
    fake_upstream.reset()
    yield


@pytest.fixture
def scenario_state() -> dict:
    """Per-scenario bag for carrying state between steps.

    Deliberately not named ``context``: pytest-playwright already defines a
    ``context`` fixture for the browser context, and shadowing it breaks the
    ``page`` fixture that depends on it.
    """
    return {}


# --------------------------------------------------------------------------
# Helpers shared by the step modules
# --------------------------------------------------------------------------


def query_string(state: dict) -> str:
    """The query accumulated by the 'Given I am viewing ...' steps."""
    params = state.get("params", {})
    if not params:
        return ""
    return "?" + "&".join(f"{k}={v}" for k, v in params.items())


def goto(state: dict, path: str) -> None:
    """Navigate, remembering the response so status can be asserted later."""
    state["response"] = state["page"].goto(f"{state['base_url']}{path}")


def tiles(page):
    return page.get_by_test_id("image-tile")


def wait_for_images(state: dict) -> None:
    """Wait until the page has settled after a navigation or control change.

    `networkidle` alone is not enough after a control change. Changing a
    control fires a JavaScript navigation, and the browser has not started it
    by the time the event handler returns — so the page is still idle from the
    *previous* load, `networkidle` is satisfied immediately, and the step goes
    on to assert against a page that never changed.

    That produced a genuinely confusing failure: the control worked, the URL
    was correct when inspected by hand, and the scenario still saw no upstream
    requests. Waiting for the URL to change first closes the race; the timeout
    is short and non-fatal because most steps navigate directly, where there is
    no pending change to wait for.
    """
    page = state["page"]
    before = page.url
    try:
        page.wait_for_function(
            "url => window.location.href !== url", arg=before, timeout=1500
        )
    except PlaywrightTimeoutError:
        pass  # nothing navigated — an ordinary step, not a control change

    page.wait_for_load_state("networkidle")


# --------------------------------------------------------------------------
# Steps shared by every feature file
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
    settings, not a structure that gets built, so there is nothing to set up.
    The step exists to make the Background's claim checkable, and fails loudly
    if the stack's catalogue size drifts from what the feature files assume.
    """
    assert count == CATALOGUE_SIZE, (
        f"the feature files assume a {count}-image catalogue but the stack "
        f"configures {CATALOGUE_SIZE}"
    )


@given(parsers.parse("I am viewing large grayscale images with blur {blur:d}"))
def viewing_large_grayscale_blur(blur: int, scenario_state):
    """Record the active variations; the navigation step applies them."""
    scenario_state["params"] = {"size": "large", "grayscale": "1", "blur": str(blur)}


@when("I open the gallery")
def open_gallery(scenario_state):
    goto(scenario_state, f"/{query_string(scenario_state)}")
    wait_for_images(scenario_state)


@when(parsers.parse('I open the gallery with size "{size}"'))
def open_with_size(size: str, scenario_state):
    """Unvalidated on purpose: the string reaches the application as written.

    This is the invalid- and custom-size family, so 'huge', '300x' and
    '6000x6000' must not be sanitised by the test.

    The size is also recorded as active, so a later step carries it — both
    'I open page 2' and 'I select the first image' read the same bag. Without
    that, those scenarios navigate without the size, lose it for a reason the
    harness invented, and report a failure the application did not cause.

    Shared rather than living beside the variation scenarios: detail.feature
    opens the gallery at a custom size too, and a step defined in one feature's
    module is not visible to another's.
    """
    scenario_state.setdefault("params", {})["size"] = size
    goto(scenario_state, f"/?size={size}")
    wait_for_images(scenario_state)


@when(parsers.parse("I open page {page:d} of the gallery"))
def open_page(page: int, scenario_state):
    params = {**scenario_state.get("params", {}), "page": str(page)}
    query = "&".join(f"{k}={v}" for k, v in params.items())
    goto(scenario_state, f"/?{query}")
    wait_for_images(scenario_state)


@when("the images have finished loading")
@then("the images have finished loading")
def images_finished_loading(scenario_state):
    """Both a 'when' and a 'then' because gallery.feature uses it in both
    positions: assert the grid is present, wait, then assert about the tiles.
    """
    wait_for_images(scenario_state)


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


def _assert_notice_mentions(scenario_state, value: str) -> None:
    """The notice must name the offending value, not merely appear.

    F3.6 is about explaining the fallback: a generic "something was wrong"
    banner would satisfy a visibility-only assertion while telling the user
    nothing about which parameter was ignored.
    """
    notice = scenario_state["page"].get_by_test_id("notice")
    expect(notice).to_be_visible()
    expect(notice).to_contain_text(value)


# Shared rather than living beside the variation scenarios: the detail page
# recovers from a bad parameter the same way the gallery does, and a step
# defined in one feature's module is invisible to another's.
@then(parsers.parse('the page explains that "{value}" is not a valid size'))
def explains_invalid_size(value: str, scenario_state):
    _assert_notice_mentions(scenario_state, value)


@then(parsers.parse('the page explains that "{value}" is not a valid blur'))
def explains_invalid_blur(value: str, scenario_state):
    _assert_notice_mentions(scenario_state, value)


@then(parsers.parse('the page explains that "{value}" is not a valid image count'))
def explains_invalid_count(value: str, scenario_state):
    _assert_notice_mentions(scenario_state, value)


@then(parsers.parse("the response status is {status:d}"))
def response_status(status: int, scenario_state):
    assert scenario_state["response"].status == status


@then(parsers.parse("the page shows {count:d} images in a grid"))
def shows_n_images(count: int, scenario_state):
    expect(tiles(scenario_state["page"])).to_have_count(count)


@then(parsers.parse("the page shows images {first:d} to {last:d}"))
def shows_image_range(first: int, last: int, scenario_state):
    """Assert both the count and the identity of the tiles.

    Identity matters: a page showing ten tiles of the wrong images would
    satisfy a count-only assertion.
    """
    located = tiles(scenario_state["page"])
    expect(located).to_have_count(last - first + 1)
    ids = located.evaluate_all("els => els.map(e => Number(e.dataset.imageId))")
    assert ids == list(range(first, last + 1))
