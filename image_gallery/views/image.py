"""`/images/<id>` — image bytes, proxied.

The only view that returns bytes rather than JSON, and the only one that
reaches upstream. Every `<img>` in the grid points here, so the browser never
learns picsum.dev exists (docs/adr/0003-django-as-image-proxy.md) and the
application actually downloads the images it is required to cache
(brief line 81).

This is also where docs/adr/0012-resilience-strategy.md's tiers are applied.
Because images are fetched when the browser asks for them rather than during
page assembly (docs/adr/0017-image-fetch-timing.md), a tile's fate is decided
per request, here:

    1. fresh cache   inside the TTL, preferred
    2. upstream      fetched, then cached
    3. stale cache   past the TTL but still retained — yesterday's image
                     beats no image
    4. placeholder   nothing cached and upstream unreachable

Every tier returns `200`. The request succeeded and something renderable came
back; a `5xx` would claim the application failed when it handled the failure
correctly. `X-Image-Source` names the tier so the client can count degraded
tiles, which it cannot infer from the bytes.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.views import View

from ..cache import ImageCache
from ..provider import PicsumProvider, UpstreamError
from ..validation import validate_blur, validate_grayscale, validate_size

logger = logging.getLogger("gallery.image")


class ImageProxyView(View):
    """Serve one image, from the best source available."""

    http_method_names = ["get", "head", "options"]

    def get(self, request, image_id: int):
        if not 1 <= image_id <= settings.GALLERY_CATALOGUE_SIZE:
            # No sensible substitute exists for an id outside the catalogue, so
            # this refuses rather than recovering — unlike a bad parameter,
            # which falls back (docs/adr/0006-recover-and-explain.md).
            raise Http404(f"no image {image_id}")

        size, size_rejection = validate_size(
            request.GET.get("size"),
            default=settings.GALLERY_DEFAULT_SIZE,
            minimum=settings.GALLERY_MIN_DIMENSION,
            maximum=settings.GALLERY_MAX_DIMENSION,
        )
        grayscale, grayscale_rejection = validate_grayscale(request.GET.get("grayscale"))
        blur, blur_rejection = validate_blur(
            request.GET.get("blur"), maximum=settings.GALLERY_MAX_BLUR
        )

        rejections = [
            rejection
            for rejection in (size_rejection, grayscale_rejection, blur_rejection)
            if rejection is not None
        ]
        if rejections:
            # The middleware will log the 400; this says which parameter caused
            # it, which the status line alone cannot.
            logger.info(
                "rejected image parameters",
                extra={
                    "image_id": image_id,
                    "rejected": [rejection.notice for rejection in rejections],
                },
            )
            return JsonResponse(
                {"errors": [rejection.as_dict() for rejection in rejections]}, status=400
            )

        return self._serve(image_id, size, grayscale, blur)

    def _serve(
        self, image_id: int, size: str, grayscale: bool, blur: int
    ) -> HttpResponse:
        provider = PicsumProvider()
        cache = ImageCache()
        width, height = provider.resolve_size(size)
        variation = {
            "width": width,
            "height": height,
            "grayscale": grayscale,
            "blur": blur,
        }

        fresh = cache.get_fresh(image_id=image_id, **variation)
        if fresh is not None:
            return self._respond(fresh)

        try:
            result = provider.fetch(
                image_id=image_id, size=size, grayscale=grayscale, blur=blur
            )
        except UpstreamError as exc:
            # The provider already logged why the fetch failed. What it cannot
            # log is which tier the request lands on, because that is this
            # view's decision — and it is the part that determines whether the
            # user sees an image or a hole in the grid.
            stale = cache.get_stale(image_id=image_id, **variation)
            if stale is not None:
                logger.warning(
                    "serving stale image after upstream failure",
                    extra={
                        "image_id": image_id,
                        "source": stale.source,
                        "error": type(exc).__name__,
                    },
                )
                return self._respond(stale)

            logger.error(
                "no image available, serving placeholder",
                extra={"image_id": image_id, "error": type(exc).__name__},
            )
            return self._placeholder()

        cache.store(result)
        return self._respond(result)

    @staticmethod
    def _respond(result) -> HttpResponse:
        response = HttpResponse(result.content, content_type=result.content_type)
        # Which tier answered. The client counts degraded tiles from this; the
        # bytes alone cannot distinguish a placeholder from a real image.
        response["X-Image-Source"] = result.source

        # Let the browser keep it. Without this the server cache saves the
        # upstream fetch but not the round trip, so reloading a 50-tile page
        # still issued 50 requests and moved ~1 MB — fast per request and slow
        # to a person watching the grid fill in again.
        #
        # `immutable` is a statement of fact here rather than an optimistic
        # hint: every parameter that changes the bytes is in the URL, and
        # `seed=7` at a given size returns byte-identical bytes on every
        # request (verified in docs/adr/0012-resilience-strategy.md). A cached
        # image cannot become wrong with age, so there is nothing to revalidate
        # and no correctness cost to a long max-age.
        #
        # `public`, because the bytes are the same for everyone: nothing here
        # varies by user, and there is no user.
        #
        # A max-age of zero means "do not cache" rather than "cache for no
        # time": `max-age=0, immutable` is a contradiction, and the e2e stack
        # sets zero precisely because its scenarios need every request to reach
        # the server where they can observe it.
        max_age = settings.GALLERY_BROWSER_CACHE_MAX_AGE
        response["Cache-Control"] = (
            f"public, max-age={max_age}, immutable" if max_age > 0 else "no-store"
        )
        return response

    @staticmethod
    def _placeholder() -> HttpResponse:
        """Nothing cached and upstream unreachable — the accepted cold-start
        case of docs/adr/0012-resilience-strategy.md. No storage layer can fix
        this, so it is a designed outcome rather than a gap.

        **504 with an empty body**, and both halves matter.

        An `<img>` cannot read a response header, and — measured, not assumed —
        it does not care about the status code either: Chromium fires `load`
        for a 504 whose body is a valid GIF, because the bytes decoded. The
        element's only signal to the page is `load` or `error`, so serving
        renderable bytes here would have every failed tile style itself as
        successfully loaded while showing a blank square. That is precisely the
        confusion the design system forbids: a failed tile must never look like
        one that worked, or like one still loading.

        Sending nothing decodable is therefore the only way to reach the
        client's `error` handler, which is what marks the tile failed and feeds
        the degraded count. The tile's own frame keeps the reserved space, so
        the grid still does not reflow — the placeholder box was doing that job
        already, and it does it whether or not an image ever arrives.

        Gateway Timeout is the honest status. This application is healthy; the
        upstream it proxies is not. The *page* is still 200 and the grid is
        complete — one subresource failed, which is what the banner reports.
        """
        response = HttpResponse(b"", content_type="image/gif", status=504)
        response["X-Image-Source"] = "placeholder"
        # Emphatically not cacheable, unlike every other tier. A real image is
        # immutable and worth keeping for a week; this is a statement about one
        # bad moment upstream. Letting a browser remember it would turn a
        # transient outage into a tile that stays broken until the cache
        # expires, long after the upstream recovered.
        response["Cache-Control"] = "no-store"
        return response
