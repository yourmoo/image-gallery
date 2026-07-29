"""The two-window cache: freshness and retention are separate.

Django's cache API cannot return an expired entry, so `CACHES["TIMEOUT"]` is
set to *retention* and freshness is compared in code against a timestamp stored
in the value. That comparison must live in one place or the tiering in the
views becomes untraceable (docs/adr/0013-module-structure.md).

Retention must exceed TTL, or the stale-fallback tier of
docs/adr/0012-resilience-strategy.md can never fire — an image would expire
from the cache at the same moment it stopped being fresh, leaving nothing to
fall back to.
"""

import pytest
from django.core.cache import cache
from django.test import override_settings

from image_gallery.cache import ImageCache
from image_gallery.provider import ImageResult


@pytest.fixture(autouse=True)
def _empty_cache():
    cache.clear()
    yield
    cache.clear()


def an_image(image_id=7, width=400, height=400, grayscale=False, blur=0, content=b"jpeg"):
    return ImageResult(
        content=content,
        content_type="image/jpeg",
        image_id=image_id,
        width=width,
        height=height,
        grayscale=grayscale,
        blur=blur,
        seed=str(image_id),
        source="upstream",
    )


# --- keys ----------------------------------------------------------------


def test_the_key_is_built_from_resolved_values_not_size_names():
    """ADR 11: retuning GALLERY_SIZE_LARGE must not serve stale bytes under an
    unchanged key. A key built from "large" would do exactly that."""
    key = ImageCache().key(image_id=7, width=800, height=800, grayscale=False, blur=0)

    assert "800" in key
    assert "large" not in key


def test_every_variation_gets_its_own_key():
    """id x dimensions x grayscale x blur are all part of identity."""
    c = ImageCache()
    keys = {
        c.key(image_id=7, width=400, height=400, grayscale=False, blur=0),
        c.key(image_id=8, width=400, height=400, grayscale=False, blur=0),
        c.key(image_id=7, width=800, height=800, grayscale=False, blur=0),
        c.key(image_id=7, width=400, height=400, grayscale=True, blur=0),
        c.key(image_id=7, width=400, height=400, grayscale=False, blur=5),
    }

    assert len(keys) == 5, "distinct variations must not collide"


def test_the_same_variation_produces_the_same_key():
    c = ImageCache()

    assert c.key(image_id=7, width=400, height=400, grayscale=True, blur=3) == c.key(
        image_id=7, width=400, height=400, grayscale=True, blur=3
    )


def test_the_key_carries_no_provider_vocabulary():
    """Keys are internal, but a key naming the provider is a smell that
    provider knowledge escaped the module that owns it."""
    key = ImageCache().key(image_id=7, width=400, height=400, grayscale=False, blur=0)

    assert "picsum" not in key.lower()
    assert "seed" not in key.lower()


# --- storing and reading -------------------------------------------------


def test_a_stored_image_reads_back_fresh():
    c = ImageCache()
    c.store(an_image())

    hit = c.get_fresh(image_id=7, width=400, height=400, grayscale=False, blur=0)

    assert hit is not None
    assert hit.content == b"jpeg"
    assert hit.source == "cache", "the tier that answered must be recorded"


def test_a_miss_is_none_rather_than_an_exception():
    c = ImageCache()

    assert c.get_fresh(image_id=99, width=400, height=400, grayscale=False, blur=0) is None


def test_bytes_are_stored_raw_and_never_base64():
    """ADR 18. Base64 would inflate every entry by a third for no benefit."""
    c = ImageCache()
    c.store(an_image(content=b"\xff\xd8\xff\xe0raw"))

    hit = c.get_fresh(image_id=7, width=400, height=400, grayscale=False, blur=0)

    assert hit.content == b"\xff\xd8\xff\xe0raw"


def test_a_variation_does_not_answer_for_a_different_one():
    """The bug a shared key would cause: asking for grayscale and getting colour."""
    c = ImageCache()
    c.store(an_image(grayscale=True, content=b"grey"))

    assert c.get_fresh(image_id=7, width=400, height=400, grayscale=False, blur=0) is None


# --- the freshness window ------------------------------------------------


@override_settings(GALLERY_CACHE_TTL=300)
def test_an_entry_past_its_ttl_is_not_fresh():
    c = ImageCache(now=lambda: 1000.0)
    c.store(an_image())

    later = ImageCache(now=lambda: 1000.0 + 301)

    assert later.get_fresh(image_id=7, width=400, height=400, grayscale=False, blur=0) is None


@override_settings(GALLERY_CACHE_TTL=300)
def test_an_entry_inside_its_ttl_is_fresh():
    c = ImageCache(now=lambda: 1000.0)
    c.store(an_image())

    later = ImageCache(now=lambda: 1000.0 + 299)

    assert later.get_fresh(image_id=7, width=400, height=400, grayscale=False, blur=0)


@override_settings(GALLERY_CACHE_TTL=300)
def test_a_stale_entry_is_still_available_as_a_fallback():
    """The whole point of two windows: no longer preferred, still usable when
    upstream cannot be reached (docs/adr/0012-resilience-strategy.md)."""
    c = ImageCache(now=lambda: 1000.0)
    c.store(an_image())

    later = ImageCache(now=lambda: 1000.0 + 3000)
    stale = later.get_stale(image_id=7, width=400, height=400, grayscale=False, blur=0)

    assert stale is not None
    assert stale.content == b"jpeg"
    assert stale.source == "stale", "a stale hit must be distinguishable from a fresh one"


def test_get_stale_returns_a_fresh_entry_too():
    """It means "the best we have", not "only the expired ones" — a caller
    falling back should not have to try both windows in order."""
    c = ImageCache()
    c.store(an_image())

    assert c.get_stale(image_id=7, width=400, height=400, grayscale=False, blur=0)


def test_nothing_cached_means_no_stale_fallback_either():
    """A cold start during an outage has no answer, and that is accepted rather
    than solved (docs/adr/0012-resilience-strategy.md)."""
    c = ImageCache()

    assert c.get_stale(image_id=1, width=400, height=400, grayscale=False, blur=0) is None
