"""Cached image bytes, with freshness and retention as separate windows.

Django's cache API cannot return an expired entry, so `CACHES["TIMEOUT"]` is
set to **retention** and freshness is compared here against a timestamp stored
alongside the bytes. Keeping that comparison in one module is what lets the
tiering read as intent — `get_fresh()` then `get_stale()` — rather than as a
scattered arithmetic on timestamps (docs/adr/0013-module-structure.md).

The two windows exist so an image can stop being *preferred* without ceasing to
be *available*. Retention must exceed TTL or the stale-fallback tier of
docs/adr/0012-resilience-strategy.md can never fire.

Keys are built from **resolved** values — pixel dimensions, never size names —
so retuning `GALLERY_SIZE_LARGE` cannot serve yesterday's 800px bytes under a
key that now means 1000px (docs/adr/0011-cache-sizing.md).

The backend is a tmpfs FileBasedCache shared by every gunicorn worker, so a
worker-local miss does not cost an upstream fetch
(docs/adr/0018-shared-cache-in-shared-memory.md). Bytes are stored raw; base64
would inflate every entry by a third for nothing.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from django.conf import settings
from django.core.cache import cache

from .provider import ImageResult

logger = logging.getLogger("gallery.cache")

# Namespaces the keys so this cache cannot collide with anything else stored in
# the same backend.
PREFIX = "img"


class ImageCache:
    """Reads and writes image bytes, and knows what "fresh" means.

    `now` is injectable so the freshness window can be tested without sleeping
    or freezing the system clock.
    """

    def __init__(self, now: Callable[[], float] = time.time) -> None:
        self._now = now

    def key(
        self, image_id: int, width: int, height: int, grayscale: bool, blur: int
    ) -> str:
        """Identity of one image variation.

        Every parameter that changes the bytes is part of the key. Built from
        client-side identifiers and resolved pixels only: nothing here names
        the provider, so the cache survives a provider swap.
        """
        return f"{PREFIX}:{image_id}:{width}x{height}:g{int(grayscale)}:b{blur}"

    def store(self, result: ImageResult) -> None:
        """Cache an image alongside the moment it was fetched.

        The timestamp is stored rather than inferred because the backend's own
        expiry is set to retention, and freshness is a shorter window that only
        this module knows about.
        """
        key = self.key(
            result.image_id, result.width, result.height, result.grayscale, result.blur
        )
        cache.set(key, {"result": result, "stored_at": self._now()})
        logger.debug(
            "cache store", extra={"key": key, "bytes": len(result.content)}
        )

    def get_fresh(
        self, image_id: int, width: int, height: int, grayscale: bool, blur: int
    ) -> ImageResult | None:
        """The cached image, if it is still inside the freshness window."""
        key = self.key(image_id, width, height, grayscale, blur)
        entry = self._entry(image_id, width, height, grayscale, blur)
        if entry is None:
            logger.debug("cache miss", extra={"key": key, "outcome": "miss"})
            return None

        age = self._now() - entry["stored_at"]
        if age > settings.GALLERY_CACHE_TTL:
            # Present but past the TTL. Reported as its own outcome rather than
            # as a miss: the bytes are still here, and whether they get used is
            # the caller's decision after upstream has had its chance.
            logger.debug(
                "cache expired",
                extra={"key": key, "outcome": "expired", "age_s": round(age, 1)},
            )
            return None

        logger.debug(
            "cache hit",
            extra={"key": key, "outcome": "hit", "age_s": round(age, 1)},
        )
        return self._tag(entry["result"], "cache")

    def get_stale(
        self, image_id: int, width: int, height: int, grayscale: bool, blur: int
    ) -> ImageResult | None:
        """The best cached copy, fresh or not.

        Means "the best we have" rather than "only the expired ones": a caller
        falling back after an upstream failure should not have to try both
        windows in order. The returned `source` distinguishes them.
        """
        key = self.key(image_id, width, height, grayscale, blur)
        entry = self._entry(image_id, width, height, grayscale, blur)
        if entry is None:
            # Reached only after upstream already failed, so this is the moment
            # a tile becomes a placeholder. WARNING, not DEBUG: it is the last
            # tier before the user sees a hole in the grid.
            logger.warning(
                "cache miss with no fallback", extra={"key": key, "outcome": "miss"}
            )
            return None

        age = self._now() - entry["stored_at"]
        source = "cache" if age <= settings.GALLERY_CACHE_TTL else "stale"
        logger.info(
            "serving cached copy after upstream failure",
            extra={"key": key, "outcome": source, "age_s": round(age, 1)},
        )
        return self._tag(entry["result"], source)

    # -- internals -------------------------------------------------------

    def _entry(self, image_id, width, height, grayscale, blur) -> dict | None:
        entry = cache.get(self.key(image_id, width, height, grayscale, blur))
        return entry if isinstance(entry, dict) and "result" in entry else None

    @staticmethod
    def _tag(result: ImageResult, source: str) -> ImageResult:
        """Record which tier answered, so callers can count degraded tiles and
        logs can tell a fresh fetch from a stale fallback without inferring it.
        """
        return ImageResult(
            content=result.content,
            content_type=result.content_type,
            image_id=result.image_id,
            width=result.width,
            height=result.height,
            grayscale=result.grayscale,
            blur=result.blur,
            seed=result.seed,
            source=source,
        )
