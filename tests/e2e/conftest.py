"""Fixtures for the browser-driven BDD suite.

Two long-lived processes back every scenario:

* a **fake upstream** standing in for picsum.dev, and
* a **Django server** pointed at it via ``GALLERY_UPSTREAM_BASE_URL``.

Both are session-scoped. Starting either per scenario would dominate the
suite's runtime, and neither needs it: the fake holds no state that a reset
cannot clear, and Django holds only the image cache.

The cache is the one exception, and it is handled explicitly. Three scenarios
in gallery.feature depend on cache state — two need it warm, one needs it
cold — so a scenario that needs a guaranteed-cold cache asks for the
``cold_cache`` fixture and gets a freshly restarted server. Everything else
shares the session's server. See the fixture for why this is preferred over
clearing the cache through a test-only endpoint.

Nothing here imports Django. Steps drive the browser and assert on the DOM;
the only non-browser observation is the fake's request log, which is how the
"no upstream image requests are made" family of steps is answered at all.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The catalogue every feature file's Background declares. Kept here so the
# "the collection holds N images" step has something to assert against.
CATALOGUE_SIZE = 100

# Short enough that the "does not respond in time" scenario fails fast, long
# enough that a healthy fake never trips it.
UPSTREAM_TIMEOUT = 1.0

# How long the fake sleeps when asked to hang: comfortably past the timeout
# above, so the request is abandoned upstream rather than merely being slow.
HANG_SECONDS = UPSTREAM_TIMEOUT * 3

# A 1x1 GIF. Real bytes matter: the browser must decode these as images, so
# the "N images are shown" steps can distinguish a rendered tile from a broken
# one. A GIF rather than a JPEG because the canonical 1x1 is 42 bytes and
# needs no encoder to produce.
#
# Dimensions are not honoured — no scenario inspects the pixels, only the
# width/height the *application* requested, which is read from the request log.
_PIXEL_GIF = bytes.fromhex(
    "47494638396101000100800000000000ffffff"
    "21f90401000000002c00000000010001000002"
    "0144003b"
)


@dataclass
class UpstreamFaults:
    """What the fake should do wrong, and for which images.

    Reset between scenarios. Every field is inert by default, so a scenario
    that sets nothing gets a healthy upstream.
    """

    outage: bool = False
    """Every request fails, as if picsum.dev were down entirely."""

    hang: bool = False
    """Every request sleeps past the client's timeout."""

    fail_seeds: set[int] = field(default_factory=set)
    """Only these seeds fail. Used by the partial-failure scenarios."""


@dataclass
class UpstreamRequest:
    """One request the application made to the fake."""

    path: str
    width: int | None
    height: int | None
    seed: int | None
    grayscale: bool
    blur: int


class FakeUpstream:
    """An in-process stand-in for picsum.dev.

    Serves the vocabulary described in docs/adr/0009-url-vocabularies.md —
    ``/{width}/{height}?seed=N&grayscale=1&blur=M`` — and records every
    request so steps can assert on how many calls the application made and
    with what parameters.
    """

    def __init__(self) -> None:
        self.faults = UpstreamFaults()
        self._requests: list[UpstreamRequest] = []
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        handler = _make_handler(self)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        assert self._server is not None, "fake upstream not started"
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    # -- recording -----------------------------------------------------

    def record(self, request: UpstreamRequest) -> None:
        with self._lock:
            self._requests.append(request)

    @property
    def requests(self) -> list[UpstreamRequest]:
        """Every request since the last reset, in order."""
        with self._lock:
            return list(self._requests)

    @property
    def image_requests(self) -> list[UpstreamRequest]:
        """Requests that asked for an image.

        Distinguished from anything else the application might probe the
        upstream for, so "no upstream image requests are made" stays true to
        its wording.
        """
        with self._lock:
            return [r for r in self._requests if r.seed is not None]

    def reset(self) -> None:
        """Clear the log and every injected fault.

        Called between scenarios. Without this the request counts leak from
        one scenario into the next, which would make the upstream-call
        assertions meaningless.
        """
        with self._lock:
            self._requests.clear()
        self.faults = UpstreamFaults()


def _make_handler(fake: FakeUpstream):
    class Handler(BaseHTTPRequestHandler):
        # Silence per-request logging to stderr; the suite has its own report.
        def log_message(self, *args) -> None:  # noqa: A003
            pass

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            parts = [p for p in parsed.path.split("/") if p]

            def _int(name: str) -> int | None:
                raw = query.get(name, [None])[0]
                try:
                    return int(raw) if raw is not None else None
                except ValueError:
                    return None

            width = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None
            height = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            seed = _int("seed")

            fake.record(
                UpstreamRequest(
                    path=self.path,
                    width=width,
                    height=height,
                    seed=seed,
                    grayscale=query.get("grayscale", ["0"])[0] in ("1", "true", "on"),
                    blur=_int("blur") or 0,
                )
            )

            faults = fake.faults
            if faults.hang:
                time.sleep(HANG_SECONDS)

            if faults.outage or (seed is not None and seed in faults.fail_seeds):
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "unavailable"}).encode())
                return

            self.send_response(200)
            self.send_header("Content-Type", "image/gif")
            self.send_header("Content-Length", str(len(_PIXEL_GIF)))
            self.end_headers()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(_PIXEL_GIF)

    return Handler


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_healthy(base_url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
        time.sleep(0.15)
    raise RuntimeError(f"server at {base_url} never became healthy: {last}")


class DjangoServer:
    """A Django process under the suite's control.

    Run from the repository root via ``python -m django`` rather than
    ``image_gallery/manage.py``: executing the latter puts the package
    directory on ``sys.path``, where ``image_gallery/logging.py`` shadows the
    standard library's ``logging`` and the process dies on a circular import.
    """

    def __init__(self, upstream_base_url: str) -> None:
        self.upstream_base_url = upstream_base_url
        self.port = _free_port()
        self._process: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "image_gallery.settings",
            "DJANGO_DEBUG": "false",
            "DJANGO_ALLOWED_HOSTS": "*",
            "DJANGO_LOG_LEVEL": "WARNING",
            "GALLERY_UPSTREAM_BASE_URL": self.upstream_base_url,
            "GALLERY_CATALOGUE_SIZE": str(CATALOGUE_SIZE),
            "GALLERY_UPSTREAM_TIMEOUT": str(UPSTREAM_TIMEOUT),
            # One attempt per image. Retries would multiply the upstream call
            # counts the scenarios assert on.
            "GALLERY_UPSTREAM_RETRIES": "0",
        }
        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "django",
                "runserver",
                str(self.port),
                "--noreload",
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_until_healthy(self.base_url)
        except RuntimeError:
            self.stop()
            raise

    def stop(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        self._process = None


@pytest.fixture(scope="session")
def fake_upstream():
    """The stand-in for picsum.dev, shared by every scenario."""
    fake = FakeUpstream()
    fake.start()
    try:
        yield fake
    finally:
        fake.stop()


@pytest.fixture(scope="session")
def _session_server(fake_upstream):
    """The Django process shared by every scenario that tolerates a warm cache."""
    server = DjangoServer(fake_upstream.base_url)
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def gallery_server(_session_server, request):
    """The server a scenario should drive.

    Normally the session's server, started once and shared. A scenario listed
    in COLD_CACHE_SCENARIOS gets a freshly started process instead, so images
    cached by an earlier scenario cannot make it pass for the wrong reason.
    """
    if _wants_cold_cache(request):
        return request.getfixturevalue("cold_cache")
    return _session_server


@pytest.fixture
def cold_cache(fake_upstream):
    """A server with a guaranteed-empty image cache.

    Restarting the process is the only way to clear a LocMemCache from
    outside it. The alternative — a test-only flush endpoint — would put test
    scaffolding into production code, which the project's SOLID and 12-factor
    guardrails rule out. Restart is slower but honest, and only three
    scenarios pay for it.
    """
    server = DjangoServer(fake_upstream.base_url)
    server.start()
    try:
        yield server
    finally:
        server.stop()


# Scenarios whose outcome depends on the cache being empty. Everything else
# shares the session's server; these get a freshly started one so images
# cached by an earlier scenario cannot make them pass for the wrong reason.
#
# Matched against the generated test name, which pytest-bdd derives from the
# scenario title. A retitled scenario silently drops off this list, so the
# check below fails the run rather than letting that pass unnoticed.
COLD_CACHE_SCENARIOS = {
    "test_images_never_seen_before_are_shown_as_unavailable",
    "test_a_slow_gallery_does_not_hold_the_page_open_indefinitely",
    "test_the_grid_appears_before_the_images_do",
}


def _wants_cold_cache(request) -> bool:
    """Whether the running scenario needs a guaranteed-empty cache.

    Decided from the test's own name at request time. Marker- and
    fixturename-based approaches were tried first and do not work here:
    pytest-bdd generates its items late enough that a collection hook cannot
    influence their fixture closure.
    """
    name = getattr(request.node, "originalname", None) or request.node.name
    return name in COLD_CACHE_SCENARIOS


@pytest.fixture(autouse=True)
def _reset_upstream(fake_upstream):
    """Clear the request log and injected faults before every scenario.

    Autouse: a scenario that forgets this would silently inherit the previous
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
