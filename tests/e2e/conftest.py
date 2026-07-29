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
# scenario run warm — tests/unit/test_bdd_harness.py fails the build if that
# happens.
COLD_CACHE_SCENARIOS = {
    "test_images_never_seen_before_are_shown_as_unavailable",
    "test_a_slow_gallery_does_not_hold_the_page_open_indefinitely",
    "test_the_grid_appears_before_the_images_do",
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

    Restarting the container is the only way to clear a LocMemCache from
    outside the process. A test-only flush endpoint would put scaffolding into
    production code, which the project's guardrails rule out. Only the
    scenarios in COLD_CACHE_SCENARIOS pay the restart cost.
    """
    _compose("restart", "web")
    _wait_for(f"{WEB_BASE_URL}/healthz", what="web")
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
