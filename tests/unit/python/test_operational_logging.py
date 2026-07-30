"""Cache tiering and upstream calls, as seen from the log stream.

The tiering in cache.py and provider.py already decides which source answers a
request. These tests cover the part that makes that decision visible: whether
a cache lookup hit, missed, or expired, and what each call to picsum.dev sent
and got back.
"""

import logging
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from image_gallery.cache import ImageCache
from image_gallery.provider import ImageResult, PicsumProvider, UpstreamError

JPEG = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


@pytest.fixture(autouse=True)
def _empty_cache():
    cache.clear()
    yield
    cache.clear()


def a_result(image_id=1, width=400, height=400, **kw):
    return ImageResult(
        content=JPEG,
        content_type="image/jpeg",
        image_id=image_id,
        width=width,
        height=height,
        seed=str(image_id),
        source="upstream",
        **kw,
    )


def variation(**kw):
    return {"width": 400, "height": 400, "grayscale": False, "blur": 0, **kw}


def record_for(caplog, message: str):
    matches = [r for r in caplog.records if r.message == message]
    assert matches, f"no {message!r} record in {[r.message for r in caplog.records]}"
    return matches[0]


def messages(caplog, name: str) -> list[str]:
    return [r.message for r in caplog.records if r.name == name]


# --- cache hit and miss --------------------------------------------------


def test_a_miss_is_logged_with_its_key(caplog):
    with caplog.at_level(logging.DEBUG, logger="gallery.cache"):
        ImageCache().get_fresh(image_id=1, **variation())

    record = record_for(caplog, "cache miss")
    assert record.outcome == "miss"
    assert record.key == "img:1:400x400:g0:b0"


def test_a_hit_is_logged_with_its_key_and_age(caplog):
    ImageCache(now=lambda: 100.0).store(a_result())

    with caplog.at_level(logging.DEBUG, logger="gallery.cache"):
        ImageCache(now=lambda: 130.0).get_fresh(image_id=1, **variation())

    record = record_for(caplog, "cache hit")
    assert record.outcome == "hit"
    assert record.key == "img:1:400x400:g0:b0"
    assert record.age_s == 30.0


@override_settings(GALLERY_CACHE_TTL=60)
def test_an_expired_entry_is_distinguished_from_a_miss(caplog):
    """The bytes are still there. Whether they get used is decided later, by
    the caller, after upstream has had its chance — so this is not a miss."""
    ImageCache(now=lambda: 100.0).store(a_result())

    with caplog.at_level(logging.DEBUG, logger="gallery.cache"):
        ImageCache(now=lambda: 1000.0).get_fresh(image_id=1, **variation())

    record = record_for(caplog, "cache expired")
    assert record.outcome == "expired"
    assert record.age_s == 900.0


def test_a_store_logs_the_byte_count(caplog):
    with caplog.at_level(logging.DEBUG, logger="gallery.cache"):
        ImageCache().store(a_result())

    assert record_for(caplog, "cache store").bytes == len(JPEG)


def test_the_key_distinguishes_variations(caplog):
    """Every parameter that changes the bytes is in the key, so the log line
    identifies which variation was looked up, not just which image."""
    with caplog.at_level(logging.DEBUG, logger="gallery.cache"):
        ImageCache().get_fresh(image_id=7, **variation(grayscale=True, blur=3))

    assert record_for(caplog, "cache miss").key == "img:7:400x400:g1:b3"


# --- the fallback path is louder than the happy one ----------------------


@override_settings(GALLERY_CACHE_TTL=60)
def test_serving_a_stale_copy_is_logged_at_info(caplog):
    ImageCache(now=lambda: 100.0).store(a_result())

    with caplog.at_level(logging.DEBUG, logger="gallery.cache"):
        ImageCache(now=lambda: 1000.0).get_stale(image_id=1, **variation())

    record = record_for(caplog, "serving cached copy after upstream failure")
    assert record.levelno == logging.INFO
    assert record.outcome == "stale"


def test_having_nothing_to_fall_back_to_is_a_warning(caplog):
    """Reached only after upstream already failed, so this is the moment a
    tile becomes a hole in the grid."""
    with caplog.at_level(logging.DEBUG, logger="gallery.cache"):
        ImageCache().get_stale(image_id=1, **variation())

    record = record_for(caplog, "cache miss with no fallback")
    assert record.levelno == logging.WARNING


# --- upstream requests and responses -------------------------------------


def test_the_upstream_request_is_logged_before_it_is_made(caplog):
    """A call that never returns leaves this line as the only evidence it was
    attempted."""
    with caplog.at_level(logging.INFO, logger="gallery.upstream"):
        with patch.object(
            PicsumProvider, "_get", return_value=(JPEG, "image/jpeg")
        ):
            PicsumProvider().fetch(image_id=3, size="medium")

    record = record_for(caplog, "upstream request")
    assert record.image_id == 3
    assert "seed=3" in record.url


def test_the_upstream_response_logs_status_and_size(caplog):
    with caplog.at_level(logging.INFO, logger="gallery.upstream"):
        with patch.object(
            PicsumProvider, "_get", return_value=(JPEG, "image/jpeg")
        ):
            PicsumProvider().fetch(image_id=3, size="medium")

    record = record_for(caplog, "upstream response")
    assert record.status == 200
    assert record.bytes == len(JPEG)
    assert record.content_type == "image/jpeg"
    assert isinstance(record.duration_ms, float)


@override_settings(GALLERY_UPSTREAM_RETRIES=2, GALLERY_UPSTREAM_BACKOFF=0)
def test_every_attempt_is_logged_separately(caplog):
    """A success on the last retry should still show that the earlier ones
    failed, and why."""
    responses = [OSError("refused"), OSError("refused"), (JPEG, "image/jpeg")]

    with caplog.at_level(logging.INFO, logger="gallery.upstream"):
        with patch.object(PicsumProvider, "_get", side_effect=responses):
            PicsumProvider().fetch(image_id=3, size="medium")

    logged = messages(caplog, "gallery.upstream")
    assert logged.count("upstream request") == 3
    assert logged.count("upstream attempt failed") == 2
    assert logged.count("upstream response") == 1


@override_settings(GALLERY_UPSTREAM_RETRIES=2, GALLERY_UPSTREAM_BACKOFF=0)
def test_attempts_are_numbered(caplog):
    with caplog.at_level(logging.INFO, logger="gallery.upstream"):
        with patch.object(PicsumProvider, "_get", side_effect=OSError("refused")):
            with pytest.raises(UpstreamError):
                PicsumProvider().fetch(image_id=3, size="medium")

    numbers = [
        r.attempt for r in caplog.records if r.message == "upstream request"
    ]
    assert numbers == [1, 2, 3]


@override_settings(GALLERY_UPSTREAM_RETRIES=0)
def test_exhausting_every_attempt_is_an_error(caplog):
    """The individual attempts were warnings because a retry might still save
    them. Nothing can save this one."""
    with caplog.at_level(logging.INFO, logger="gallery.upstream"):
        with patch.object(PicsumProvider, "_get", side_effect=OSError("refused")):
            with pytest.raises(UpstreamError):
                PicsumProvider().fetch(image_id=3, size="medium")

    record = record_for(caplog, "upstream fetch failed")
    assert record.levelno == logging.ERROR
    assert record.error == "OSError"
    assert record.attempts == 1


@override_settings(GALLERY_UPSTREAM_RETRIES=0)
def test_the_failure_names_the_exception_type(caplog):
    """`str(exc)` alone is often empty for a timeout — the class name is what
    makes the line diagnosable."""
    with caplog.at_level(logging.INFO, logger="gallery.upstream"):
        with patch.object(PicsumProvider, "_get", side_effect=TimeoutError()):
            with pytest.raises(UpstreamError):
                PicsumProvider().fetch(image_id=3, size="medium")

    assert record_for(caplog, "upstream attempt failed").error == "TimeoutError"


# --- the view's own fallback decision ------------------------------------


def test_falling_back_to_a_placeholder_is_logged(client, caplog):
    """The provider logs why the fetch failed; only the view knows which tier
    the request actually landed on."""
    with caplog.at_level(logging.INFO, logger="gallery.image"):
        with patch(
            "image_gallery.views.image.PicsumProvider.fetch",
            side_effect=UpstreamError("down"),
        ):
            client.get(reverse("image", args=[1]))

    record = record_for(caplog, "no image available, serving placeholder")
    assert record.levelno == logging.ERROR
    assert record.image_id == 1


def test_falling_back_to_stale_bytes_is_logged(client, caplog):
    ImageCache().store(a_result())

    with caplog.at_level(logging.INFO, logger="gallery.image"):
        with patch(
            "image_gallery.views.image.PicsumProvider.fetch",
            side_effect=UpstreamError("down"),
        ):
            with patch(
                "image_gallery.views.image.ImageCache.get_fresh", return_value=None
            ):
                client.get(reverse("image", args=[1]))

    assert record_for(caplog, "serving stale image after upstream failure").image_id == 1


def test_a_rejected_parameter_names_itself(client, caplog):
    """The middleware logs the 400; this says which parameter caused it."""
    with caplog.at_level(logging.INFO, logger="gallery.image"):
        client.get(reverse("image", args=[1]), {"blur": "999"})

    # The notice carries the offending value too, which is the part that makes
    # the line actionable without re-reading the query string.
    assert record_for(caplog, "rejected image parameters").rejected == [
        "invalid_blur:999"
    ]
