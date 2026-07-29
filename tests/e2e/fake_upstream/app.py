"""A stand-in for picsum.dev, run as its own container for the e2e suite.

Serves the upstream vocabulary described in docs/adr/0009-url-vocabularies.md
— ``/{width}/{height}?seed=N&grayscale=1&blur=M`` — and records every request
so the suite can assert how many calls the application made and with what
parameters.

Because the tests run in a different process from this one, faults and the
request log are driven over HTTP through a small control API under
``/_control``. That surface exists only here, in test infrastructure; the
application image stays free of test scaffolding.

Deliberately dependency-free (standard library only) so the image is tiny and
builds without a package index.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8000

# How long a "hang" sleeps. The suite sets the application's upstream timeout
# well below this, so a hung request is abandoned rather than merely slow.
DEFAULT_HANG_SECONDS = 5.0

# A 1x1 GIF: real bytes, so the browser decodes a tile as an image and the
# "N images are shown" steps can tell a rendered tile from a broken one.
# Dimensions are not honoured -- no scenario inspects pixels, only the
# width/height the application *requested*, which is read from the log.
PIXEL_GIF = bytes.fromhex(
    "47494638396101000100800000000000ffffff"
    "21f90401000000002c00000000010001000002"
    "0144003b"
)


@dataclass
class Faults:
    """What the fake should do wrong, and for which images."""

    outage: bool = False
    """Every image request fails, as if picsum.dev were down entirely."""

    hang: bool = False
    """Every image request sleeps past the application's timeout."""

    hang_seconds: float = DEFAULT_HANG_SECONDS

    fail_seeds: list[int] = field(default_factory=list)
    """Only these seeds fail. Used by the partial-failure scenarios."""


@dataclass
class RecordedRequest:
    """One request the application made to this fake."""

    path: str
    width: int | None
    height: int | None
    seed: int | None
    grayscale: bool
    blur: int


class State:
    """Mutable server state, guarded by a lock.

    Threaded server plus a control API means concurrent mutation is normal,
    not exceptional: the application fetches a page's images in parallel while
    the suite may be reading the log.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.faults = Faults()
        self._requests: list[RecordedRequest] = []

    def record(self, request: RecordedRequest) -> None:
        with self._lock:
            self._requests.append(request)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [asdict(r) for r in self._requests]

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self.faults = Faults()

    def set_faults(self, payload: dict) -> None:
        with self._lock:
            self.faults = Faults(
                outage=bool(payload.get("outage", False)),
                hang=bool(payload.get("hang", False)),
                hang_seconds=float(payload.get("hang_seconds", DEFAULT_HANG_SECONDS)),
                fail_seeds=[int(s) for s in payload.get("fail_seeds", [])],
            )

    def current_faults(self) -> Faults:
        with self._lock:
            return Faults(
                outage=self.faults.outage,
                hang=self.faults.hang,
                hang_seconds=self.faults.hang_seconds,
                fail_seeds=list(self.faults.fail_seeds),
            )


STATE = State()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # noqa: A003
        """Silence per-request logging; the suite has its own report."""

    # -- helpers -------------------------------------------------------

    def _send_json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    # -- routes --------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path

        if path == "/_control/health":
            self._send_json(200, {"status": "ok"})
            return

        if path == "/_control/requests":
            self._send_json(200, STATE.snapshot())
            return

        self._serve_image()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path

        if path == "/_control/reset":
            STATE.reset()
            self._send_json(200, {"reset": True})
            return

        if path == "/_control/faults":
            STATE.set_faults(self._read_json())
            self._send_json(200, asdict(STATE.current_faults()))
            return

        self._send_json(404, {"error": "not found"})

    # -- the image endpoint --------------------------------------------

    def _serve_image(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        parts = [p for p in parsed.path.split("/") if p]

        def _int(name: str) -> int | None:
            raw = query.get(name, [None])[0]
            try:
                return int(raw) if raw is not None else None
            except (TypeError, ValueError):
                return None

        width = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else None
        height = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        seed = _int("seed")

        STATE.record(
            RecordedRequest(
                path=self.path,
                width=width,
                height=height,
                seed=seed,
                grayscale=query.get("grayscale", ["0"])[0] in ("1", "true", "on"),
                blur=_int("blur") or 0,
            )
        )

        faults = STATE.current_faults()

        if faults.hang:
            time.sleep(faults.hang_seconds)

        if faults.outage or (seed is not None and seed in faults.fail_seeds):
            self._send_json(503, {"error": "unavailable"})
            return

        self.send_response(200)
        self.send_header("Content-Type", "image/gif")
        self.send_header("Content-Length", str(len(PIXEL_GIF)))
        self.end_headers()
        self.wfile.write(PIXEL_GIF)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
