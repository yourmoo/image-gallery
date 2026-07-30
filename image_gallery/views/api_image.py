"""`/api/images/<id>` — everything the detail page needs, as JSON.

The detail page is a shell: the server sends markup and a script, and this
endpoint sends the content (docs/adr/0022-the-detail-page-joins-the-client.md).
That is the same split the gallery already uses, so the application now has one
rendering model rather than two.

**It reports resolved values, which is why it has to exist.** ADR 7 forces the
detail view's size up — browsing at `small` and opening an image gives `large` —
and the client cannot derive that from the URL it was opened with. The
parameters panel exists to disclose the substitution (F4.4), so the value it
reports has to come from whoever performed it.

**Rejected parameters are reported here, not redirected away.** The endpoint
answers `200` with the fallback applied and a `notices` array explaining what
happened; the client renders the banner and tidies the address bar itself. The
requirement is that a user who asks for something unavailable is *recovered and
told* — it never asked for a `3xx`, and doing it in one response spares the
browser a second round trip.

The sentences are built here rather than in JavaScript so the wording has one
home. They quote configured bounds ("between 16 and 1600"), and a copy in the
client would go stale the moment `GALLERY_MAX_DIMENSION` was retuned.

**No upstream I/O.** Every field comes from the request and from configuration,
so this answers at local speed even while picsum is down
(docs/adr/0017-image-fetch-timing.md). It cannot report that an image failed to
load — that is not known until the bytes are fetched, which is the `<img>`
element's business.
"""

from __future__ import annotations

from django.conf import settings
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.views import View

from ..detail import detail_size
from ..validation import (
    NAMED_SIZES,
    default_bounds,
    notice_messages,
    validate,
    validate_size,
)

# The parameters the page's two size controls submit, in precedence order: the
# typed field beats the dropdown, being the more specific intent.
SIZE_PARAMETERS = ("custom_detail_size", "detail_size")


class ImageApiView(View):
    """One image, described. No bytes, no upstream call."""

    http_method_names = ["get", "head", "options"]

    def get(self, request, image_id: int):
        if not 1 <= image_id <= settings.GALLERY_CATALOGUE_SIZE:
            # No sensible substitute exists for an id outside the catalogue, so
            # this refuses rather than recovering — unlike a bad parameter,
            # which falls back (docs/adr/0006-recover-and-explain.md).
            raise Http404(f"no image {image_id}")

        result = validate(
            request.GET,
            page_sizes=settings.GALLERY_PAGE_SIZES,
            default_count=settings.GALLERY_DEFAULT_PAGE_SIZE,
            catalogue_size=settings.GALLERY_CATALOGUE_SIZE,
            default_size=settings.GALLERY_DEFAULT_SIZE,
            minimum_dimension=settings.GALLERY_MIN_DIMENSION,
            maximum_dimension=settings.GALLERY_MAX_DIMENSION,
            maximum_blur=settings.GALLERY_MAX_BLUR,
        )

        # This page's own size parameter, which `validate` does not see because
        # it speaks the gallery's vocabulary. Checked here and its rejection
        # joined to the rest, so a bad value recovers exactly like any other
        # rather than being silently ignored.
        chosen = self._chosen_size(request)
        rejections = list(result.rejections)
        size = detail_size(result.size, large=settings.GALLERY_SIZE_LARGE)

        if chosen is not None:
            resolved, rejection = validate_size(
                chosen,
                default="large",
                minimum=settings.GALLERY_MIN_DIMENSION,
                maximum=settings.GALLERY_MAX_DIMENSION,
            )
            if rejection is None:
                size = resolved
            else:
                rejections.append(rejection)

        return JsonResponse(self._payload(image_id, size, result, rejections))

    @staticmethod
    def _chosen_size(request) -> str | None:
        """The size the user picked on this page, from either control.

        Both parameters are read with `getlist` and scanned for the first
        non-empty value, because a browser submits *every* control in a form. A
        `<select>` whose value is empty, or a field left blank, arrives as
        `detail_size=` alongside the real choice — and `.get()` returns the
        last, so an empty control silently overrode every selection.
        """
        for name in SIZE_PARAMETERS:
            for value in request.GET.getlist(name):
                if value.strip():
                    return value
        return None

    def _payload(self, image_id: int, size: str, result, rejections) -> dict:
        """The whole page, as data.

        Keys are camelCase: this is the client's vocabulary, and the client is
        JavaScript. Nothing here names the provider — no `seed`, no upstream
        host — because that boundary holds regardless of which format the
        answer travels in (docs/adr/0009-url-vocabularies.md).
        """
        return {
            "id": image_id,
            # Complete, and used verbatim. The server builds it by reversing
            # the route (F5.2, F5.4), so no URL-construction rule lives in
            # JavaScript and the client cannot assemble a path of its own.
            "url": self._image_url(image_id, size, result),
            "backUrl": self._back_url(result),
            # Resolved, not requested. The difference is the point (F4.4).
            "size": size,
            "grayscale": result.grayscale,
            "blur": result.blur,
            # Empty unless a custom size is active: a `<select>` can only show
            # a value it lists, so the two controls split the job between them.
            "customSize": "" if size in NAMED_SIZES else size,
            "namedSizes": list(NAMED_SIZES),
            "maxBlur": settings.GALLERY_MAX_BLUR,
            "notices": self._notices(rejections),
        }

    @staticmethod
    def _notices(rejections) -> list[dict]:
        """What was rejected, and the sentence explaining it.

        `code` and `value` travel alongside the prose so a client can act on
        the rejection — highlight the offending control, say — without parsing
        English. The message is the part a person reads.
        """
        bounds = default_bounds()
        return [
            {
                "code": f"invalid_{rejection.parameter}",
                "value": str(rejection.value),
                "message": notice_messages([rejection.notice], bounds=bounds)[0],
            }
            for rejection in rejections
        ]

    @staticmethod
    def _image_url(image_id: int, size: str, result) -> str:
        """The proxy URL for the bytes: ADR 7's two halves in one URL."""
        params = {"size": size}
        if result.grayscale:
            params["grayscale"] = "1"
        if result.blur:
            params["blur"] = str(result.blur)

        query = "&".join(f"{name}={value}" for name, value in params.items())
        return f"{reverse('image', args=[image_id])}?{query}"

    @staticmethod
    def _back_url(result) -> str:
        """Back to the gallery, restoring page and filters (F4.1).

        The **gallery's** size, not this page's: returning to a grid rendered
        at `large` when the user left one rendered at `small` would be a change
        they never asked for.
        """
        params = []
        if result.page != 1:
            params.append(f"page={result.page}")
        if result.count != settings.GALLERY_DEFAULT_PAGE_SIZE:
            params.append(f"count={result.count}")
        if result.size != settings.GALLERY_DEFAULT_SIZE:
            params.append(f"size={result.size}")
        if result.grayscale:
            params.append("grayscale=1")
        if result.blur:
            params.append(f"blur={result.blur}")

        index = reverse("index")
        return f"{index}?{'&'.join(params)}" if params else index
