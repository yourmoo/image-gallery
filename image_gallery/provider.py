"""The image provider, and the only module that knows picsum.dev exists.

This is the swappable component of docs/adr/0005-service-layer-boundary.md.
Replacing the provider means rewriting this file and its tests, and nothing
else — which is checkable rather than aspirational: grep for `picsum` and every
hit should be here, in this module's tests, or in documentation.

It performs both translations of docs/adr/0009-url-vocabularies.md:

    client vocabulary          provider vocabulary
    id 7                  ->   seed=7
    size "medium"         ->   /400/400

**The client's query string is never forwarded**, even where names coincide.
`size=medium` means nothing upstream, and passing it through would leak client
vocabulary across the boundary this module exists to hold.

`fetch` returns an `ImageResult` rather than raw bytes, carrying the values
actually used to produce the image. Callers would otherwise re-derive them to
satisfy F4.4, duplicating logic only this module can perform correctly and
letting the displayed parameters drift from what was fetched
(docs/adr/0013-module-structure.md).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger("gallery.upstream")


class UpstreamError(Exception):
    """The provider could not supply an image.

    Raised rather than returning empty bytes: empty bytes look like a
    successful fetch of a broken image, and the caller needs to distinguish
    them to choose a fallback tier (docs/adr/0012-resilience-strategy.md).
    """


@dataclass(frozen=True)
class ImageResult:
    """An image, and the values that were actually used to produce it.

    `width`/`height` are resolved pixels, which may differ from what the client
    asked for when a parameter fell back — that difference is exactly what the
    detail view's parameters panel exists to disclose (F4.4).
    """

    content: bytes
    content_type: str
    image_id: int
    width: int
    height: int
    grayscale: bool = False
    blur: int = 0
    seed: str = ""
    source: str = "upstream"
    """Which tier answered: upstream | cache | stale | placeholder."""

    def as_client_dict(self) -> dict:
        """The view of this result the browser may see.

        `seed` and `source` are deliberately absent: the first is provider
        vocabulary (ADR 9), the second is an internal diagnostic.
        """
        return {
            "id": self.image_id,
            "width": self.width,
            "height": self.height,
            "grayscale": self.grayscale,
            "blur": self.blur,
        }


class PicsumProvider:
    """Talks to picsum.dev. Nothing else in the application does.

    Reads its configuration once at construction so a caller cannot pass in a
    base URL — the environment is read only in settings.py
    (docs/adr/0008-configuration-in-settings.md).
    """

    def __init__(self) -> None:
        self.base_url = settings.GALLERY_UPSTREAM_BASE_URL.rstrip("/")
        self.timeout = settings.GALLERY_UPSTREAM_TIMEOUT
        self.retries = settings.GALLERY_UPSTREAM_RETRIES
        self.backoff = settings.GALLERY_UPSTREAM_BACKOFF
        self._named_sizes = {
            "small": settings.GALLERY_SIZE_SMALL,
            "medium": settings.GALLERY_SIZE_MEDIUM,
            "large": settings.GALLERY_SIZE_LARGE,
        }

    # -- vocabulary translation ------------------------------------------

    def resolve_size(self, size: str) -> tuple[int, int]:
        """A named size or a `WxH` pair, in pixels.

        Custom dimensions are a first-class size rather than a special case
        (docs/adr/0010-configurable-and-custom-sizes.md); validation has
        already bounded them by the time they arrive here.
        """
        raw = self._named_sizes.get(size, size)
        width, _, height = str(raw).lower().partition("x")
        return int(width), int(height or width)

    def image_url(
        self,
        image_id: int,
        width: int,
        height: int,
        grayscale: bool = False,
        blur: int = 0,
    ) -> str:
        """The upstream URL for one image. Pure — no I/O.

        Defaults are omitted rather than sent explicitly: `grayscale=0` tells
        the provider what it already assumes, and keeping it out makes the URL
        (and the cache key derived from the same values) carry only what was
        actually asked for.
        """
        params = {"seed": str(image_id)}
        if grayscale:
            params["grayscale"] = "1"
        if blur:
            params["blur"] = str(blur)

        return f"{self.base_url}/{width}/{height}?{urlencode(params)}"

    # -- fetching --------------------------------------------------------

    def fetch(
        self,
        image_id: int,
        size: str,
        grayscale: bool = False,
        blur: int = 0,
    ) -> ImageResult:
        """Fetch one image, retrying on transient failure.

        Retries are bounded by configuration and the e2e stack sets them to
        zero, because a retry would multiply the upstream call counts the
        scenarios assert on.
        """
        width, height = self.resolve_size(size)
        url = self.image_url(image_id, width, height, grayscale, blur)

        last: Exception | None = None
        for attempt in range(self.retries + 1):
            # The outbound call, logged before it is made: a request that never
            # returns leaves this line as the only evidence it was attempted.
            logger.info(
                "upstream request",
                extra={
                    "url": url,
                    "image_id": image_id,
                    "attempt": attempt + 1,
                    "of": self.retries + 1,
                },
            )
            started = time.monotonic()
            try:
                content, content_type = self._get(url)
            except (URLError, HTTPError, OSError, TimeoutError) as exc:
                last = exc
                # Per-attempt, so a success on retry 2 still shows that retry 1
                # failed and why. `getattr` because only HTTPError has a code.
                logger.warning(
                    "upstream attempt failed",
                    extra={
                        "url": url,
                        "image_id": image_id,
                        "attempt": attempt + 1,
                        "status": getattr(exc, "code", None),
                        "error": type(exc).__name__,
                        "detail": str(exc),
                        "duration_ms": round((time.monotonic() - started) * 1000, 1),
                    },
                )
                if attempt < self.retries:
                    time.sleep(self.backoff * (attempt + 1))
                continue

            logger.info(
                "upstream response",
                extra={
                    "url": url,
                    "image_id": image_id,
                    "status": 200,
                    "content_type": content_type,
                    "bytes": len(content),
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                },
            )
            return ImageResult(
                content=content,
                content_type=content_type,
                image_id=image_id,
                width=width,
                height=height,
                grayscale=grayscale,
                blur=blur,
                seed=str(image_id),
                source="upstream",
            )

        # Every attempt is spent. ERROR rather than WARNING: the individual
        # attempts were warnings because a retry might still save them, and
        # nothing can save this one — the caller is about to fall back to stale
        # bytes or a placeholder.
        logger.error(
            "upstream fetch failed",
            extra={
                "url": url,
                "image_id": image_id,
                "attempts": self.retries + 1,
                "error": type(last).__name__ if last else None,
                "detail": str(last),
            },
        )
        raise UpstreamError(f"could not fetch image {image_id}: {last}") from last

    def _get(self, url: str) -> tuple[bytes, str]:
        """One HTTP attempt. The only place this application opens a socket."""
        request = Request(url, headers={"Accept": "image/*"})
        with urlopen(request, timeout=self.timeout) as response:
            return response.read(), response.headers.get("Content-Type", "image/jpeg")
