"""The provider is the only module that may name picsum.

Everything here is about the boundary of docs/adr/0009-url-vocabularies.md: the
client says `id` and `medium`, the provider says `seed` and `400x400`, and the
translation happens once, here. If this file passes and no other module names
the provider, swapping picsum.dev is a one-module change — the claim brief
line 91 makes and F5.3 is graded on.

URL construction is a pure function and is tested as one. Only the fetch path
needs a stubbed transport.
"""

from unittest.mock import patch

import pytest
from django.test import override_settings

from image_gallery.provider import ImageResult, PicsumProvider, UpstreamError

BASE = "https://example.test"


def provider(**overrides):
    settings = {
        "GALLERY_UPSTREAM_BASE_URL": BASE,
        "GALLERY_SIZE_SMALL": "200x200",
        "GALLERY_SIZE_MEDIUM": "400x400",
        "GALLERY_SIZE_LARGE": "800x800",
        **overrides,
    }
    with override_settings(**settings):
        return PicsumProvider()


# --- URL construction: the vocabulary boundary ---------------------------


def test_the_client_id_becomes_the_upstream_seed():
    """Same number, two vocabularies. Only this module knows they coincide."""
    url = provider().image_url(image_id=7, width=400, height=400)

    assert url.startswith(f"{BASE}/400/400")
    assert "seed=7" in url


def test_the_url_uses_the_provider_dimension_form():
    url = provider().image_url(image_id=1, width=200, height=300)

    assert url.startswith(f"{BASE}/200/300")


@pytest.mark.parametrize(
    "name,expected",
    [("small", (200, 200)), ("medium", (400, 400)), ("large", (800, 800))],
)
def test_named_sizes_resolve_to_configured_pixels(name, expected):
    """A deployment can retune what `large` means, so the mapping is settings."""
    assert provider().resolve_size(name) == expected


def test_named_sizes_follow_configuration_rather_than_being_hardcoded():
    assert provider(GALLERY_SIZE_LARGE="1000x750").resolve_size("large") == (1000, 750)


def test_grayscale_is_expressed_in_the_providers_own_terms():
    url = provider().image_url(image_id=3, width=400, height=400, grayscale=True)

    assert "grayscale=1" in url


def test_grayscale_off_is_omitted_rather_than_sent_as_zero():
    """A default should not appear in the URL: it makes cache keys noisier and
    tells the provider something it already assumes."""
    url = provider().image_url(image_id=3, width=400, height=400, grayscale=False)

    assert "grayscale" not in url


def test_blur_is_carried_when_set_and_omitted_when_zero():
    assert "blur=5" in provider().image_url(image_id=3, width=400, height=400, blur=5)
    assert "blur" not in provider().image_url(image_id=3, width=400, height=400, blur=0)


def test_grayscale_and_blur_combine():
    """F3.5 — the two are independent parameters, not alternatives."""
    url = provider().image_url(image_id=9, width=800, height=800, grayscale=True, blur=4)

    assert "grayscale=1" in url
    assert "blur=4" in url


def test_the_client_query_string_is_never_forwarded():
    """Even where names coincide. `size` is client vocabulary and means
    nothing upstream; only resolved pixels are sent."""
    url = provider().image_url(image_id=7, width=400, height=400)

    assert "size=" not in url
    assert "count=" not in url
    assert "page=" not in url


# --- fetching ------------------------------------------------------------


class FakeResponse:
    def __init__(self, content=b"\xff\xd8jpeg", content_type="image/jpeg", status=200):
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.status = status

    def read(self):
        return self.content

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_fetch_returns_the_bytes_and_the_values_used_to_produce_them():
    """ADR 13: the provider returns an ImageResult, not raw bytes.

    Callers would otherwise re-derive the resolved dimensions to satisfy F4.4,
    duplicating logic only the provider can perform correctly and letting the
    displayed parameters drift from what was actually fetched.
    """
    with patch("image_gallery.provider.urlopen", return_value=FakeResponse()):
        result = provider().fetch(image_id=7, size="medium")

    assert isinstance(result, ImageResult)
    assert result.content == b"\xff\xd8jpeg"
    assert result.content_type == "image/jpeg"
    assert result.image_id == 7
    assert (result.width, result.height) == (400, 400)
    assert result.source == "upstream"


def test_the_result_carries_the_seed_for_logs_but_it_is_provider_vocabulary():
    """Carried, never rendered — ADR 9. The parameters panel says "Image 7"."""
    with patch("image_gallery.provider.urlopen", return_value=FakeResponse()):
        result = provider().fetch(image_id=7, size="medium")

    assert result.seed == "7"
    assert "seed" not in result.as_client_dict()


def test_an_upstream_failure_raises_rather_than_returning_empty_bytes():
    """The caller decides what to serve instead (ADR 12's tiers). Returning
    empty bytes would look like a successful fetch of a broken image."""
    with patch("image_gallery.provider.urlopen", side_effect=OSError("refused")):
        with pytest.raises(UpstreamError):
            provider().fetch(image_id=7, size="medium")


def test_a_timeout_is_an_upstream_error_like_any_other():
    with patch("image_gallery.provider.urlopen", side_effect=TimeoutError):
        with pytest.raises(UpstreamError):
            provider().fetch(image_id=7, size="medium")


@override_settings(GALLERY_UPSTREAM_RETRIES=2, GALLERY_UPSTREAM_BACKOFF=0)
def test_a_failed_fetch_is_retried_up_to_the_configured_limit():
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise OSError("transient")
        return FakeResponse()

    with patch("image_gallery.provider.urlopen", side_effect=flaky):
        result = PicsumProvider().fetch(image_id=7, size="medium")

    assert len(calls) == 3, "should retry twice after the first failure"
    assert result.source == "upstream"


@override_settings(GALLERY_UPSTREAM_RETRIES=0)
def test_no_retry_means_exactly_one_attempt():
    """The e2e stack sets retries to 0 so upstream call counts stay assertable."""
    calls = []

    def always_fails(*args, **kwargs):
        calls.append(1)
        raise OSError("refused")

    with patch("image_gallery.provider.urlopen", side_effect=always_fails):
        with pytest.raises(UpstreamError):
            PicsumProvider().fetch(image_id=7, size="medium")

    assert len(calls) == 1


def test_a_custom_size_is_fetched_at_those_exact_dimensions():
    """ADR 10 — `WxH` is a first-class size, not only the three names."""
    with patch("image_gallery.provider.urlopen", return_value=FakeResponse()) as opened:
        result = provider().fetch(image_id=7, size="640x480")

    assert (result.width, result.height) == (640, 480)
    assert "/640/480" in opened.call_args[0][0].full_url
