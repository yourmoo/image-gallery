"""`/images/<id>` — the only endpoint that returns bytes.

This is the proxy of docs/adr/0003-django-as-image-proxy.md: the browser asks
this application for every image and never learns picsum.dev exists. It is also
where docs/adr/0012-resilience-strategy.md's tiering is applied per request —
fresh cache, upstream, stale cache — because on-demand fetching means a tile's
fate is decided here rather than during page assembly
(docs/adr/0017-image-fetch-timing.md).
"""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from image_gallery.provider import ImageResult, UpstreamError

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


def url_for(image_id: int) -> str:
    return reverse("image", args=[image_id])


# --- serving bytes -------------------------------------------------------


def test_the_endpoint_serves_the_image_bytes(client):
    with patch("image_gallery.views.image.PicsumProvider.fetch", return_value=a_result()):
        response = client.get(url_for(1))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response.content == JPEG


def test_the_response_never_mentions_the_provider(client):
    """ADR 3: the browser must not learn picsum exists, including via headers."""
    with patch("image_gallery.views.image.PicsumProvider.fetch", return_value=a_result()):
        response = client.get(url_for(1))

    headers = " ".join(f"{k}{v}" for k, v in response.items()).lower()

    assert "picsum" not in headers
    assert "seed" not in headers


def test_an_id_outside_the_catalogue_is_a_404(client):
    """Image 101 in a 100-image catalogue has no sensible substitute, so it is
    refused rather than recovered (docs/adr/0006-recover-and-explain.md)."""
    with patch("image_gallery.views.image.PicsumProvider.fetch") as fetch:
        response = client.get(url_for(101))

    assert response.status_code == 404
    assert not fetch.called, "an out-of-range id must not reach the provider"


def test_id_zero_is_also_out_of_range(client):
    assert client.get(url_for(0)).status_code == 404


# --- the caching tiers ---------------------------------------------------


def test_the_first_request_fetches_upstream(client):
    with patch(
        "image_gallery.views.image.PicsumProvider.fetch", return_value=a_result()
    ) as fetch:
        client.get(url_for(1))

    assert fetch.call_count == 1


def test_a_second_request_is_served_from_cache_without_a_second_fetch(client):
    """F5.5, and the only requirement in F5 with a scenario: caching is
    observable because a repeat must not produce a second upstream call."""
    with patch(
        "image_gallery.views.image.PicsumProvider.fetch", return_value=a_result()
    ) as fetch:
        client.get(url_for(1))
        response = client.get(url_for(1))

    assert fetch.call_count == 1, "the second request must not reach upstream"
    assert response.content == JPEG


def test_a_different_variation_is_fetched_separately(client):
    """Cached bytes for `medium` must not answer a request for `large`."""
    with patch(
        "image_gallery.views.image.PicsumProvider.fetch", return_value=a_result()
    ) as fetch:
        client.get(url_for(1))
        client.get(url_for(1), {"size": "large"})

    assert fetch.call_count == 2


# --- resilience ----------------------------------------------------------


def test_an_upstream_failure_sends_nothing_the_browser_can_decode(client):
    """The only way to reach the client's `error` handler.

    Measured rather than assumed: Chromium fires `load`, not `error`, for a 504
    whose body is a valid GIF — the bytes decoded, so the element is satisfied
    and the status is invisible to it. Serving renderable bytes here would have
    every failed tile style itself as loaded while showing a blank square.

    The grid still does not reflow: the tile's own frame reserves the space,
    with or without an image inside it.
    """
    with patch(
        "image_gallery.views.image.PicsumProvider.fetch", side_effect=UpstreamError("down")
    ):
        response = client.get(url_for(1))

    assert response.content == b""


def test_a_failed_fetch_falls_back_to_stale_bytes_when_they_exist(client):
    """The middle tier. Yesterday's image beats no image."""
    with patch("image_gallery.views.image.PicsumProvider.fetch", return_value=a_result()):
        client.get(url_for(1))

    with override_settings(GALLERY_CACHE_TTL=-1):  # everything is now stale
        with patch(
            "image_gallery.views.image.PicsumProvider.fetch",
            side_effect=UpstreamError("down"),
        ):
            response = client.get(url_for(1))

    assert response.status_code == 200
    assert response.content == JPEG, "stale bytes should have answered"


def test_a_degraded_response_says_so_in_a_header(client):
    """The client counts failed tiles to render the degraded banner, and a
    placeholder is not distinguishable from a real image by its bytes alone."""
    with patch(
        "image_gallery.views.image.PicsumProvider.fetch", side_effect=UpstreamError("down")
    ):
        response = client.get(url_for(1))

    assert response["X-Image-Source"] == "placeholder"


def test_a_placeholder_is_a_status_the_browser_can_act_on(client):
    """`<img>` cannot read a response header, so a header alone leaves the
    client unable to tell a placeholder from a real image — and the failed-tile
    state exists precisely so the two never look alike.

    504 rather than 200: the tile's `error` event is the only signal an <img>
    gives a page, and Gateway Timeout is the honest description — this
    application is fine, the upstream it proxies is not. The *page* still
    renders 200 and the grid is complete; it is this one subresource that
    failed, which is what the degraded banner reports.
    """
    with patch(
        "image_gallery.views.image.PicsumProvider.fetch", side_effect=UpstreamError("down")
    ):
        response = client.get(url_for(1))

    assert response.status_code == 504
    assert response["X-Image-Source"] == "placeholder"


def test_a_stale_fallback_is_a_success_not_a_failure(client):
    """Serving yesterday's bytes is a working tile, not a degraded one: the
    user sees the image they expected. Only "nothing to show" is a failure."""
    with patch("image_gallery.views.image.PicsumProvider.fetch", return_value=a_result()):
        client.get(url_for(1))

    with override_settings(GALLERY_CACHE_TTL=-1):
        with patch(
            "image_gallery.views.image.PicsumProvider.fetch",
            side_effect=UpstreamError("down"),
        ):
            response = client.get(url_for(1))

    assert response.status_code == 200
    assert response["X-Image-Source"] == "stale"


def test_a_served_image_reports_which_tier_answered(client):
    with patch("image_gallery.views.image.PicsumProvider.fetch", return_value=a_result()):
        assert client.get(url_for(1))["X-Image-Source"] == "upstream"
        assert client.get(url_for(1))["X-Image-Source"] == "cache"


# --- parameters ----------------------------------------------------------


def test_the_requested_size_reaches_the_provider(client):
    with patch(
        "image_gallery.views.image.PicsumProvider.fetch", return_value=a_result()
    ) as fetch:
        client.get(url_for(1), {"size": "large"})

    assert fetch.call_args.kwargs["size"] == "large"


def test_an_invalid_size_is_rejected_rather_than_guessed(client):
    """The client builds requests from allow-listed controls, so a bad value
    here is a client bug or a hand-edited URL — ADR 19."""
    response = client.get(url_for(1), {"size": "enormous"})

    assert response.status_code == 400
    assert response["Content-Type"].startswith("application/json")
    assert response.json()["errors"][0]["parameter"] == "size"
