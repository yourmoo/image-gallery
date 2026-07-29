"""`/images/<id>` — one image, on its own page.

A **page**, not bytes: `/img/<id>` serves those. Two routes because a user
links to and bookmarks the first while an `<img>` element fetches the second,
and a single path cannot be both.

Like the shell, this is a document boundary: a pasted URL with a bad parameter
is corrected here and explained, rather than refused
(docs/adr/0019-validation-errors-carry-a-usable-payload.md). An id outside the
catalogue is the exception — it has no sensible substitute, so it is a 404.

The view's own rule is `detail.detail_size`: size is forced up, filters carry
over untouched (docs/adr/0007-detail-view-size.md). Because that silently
changes one of the user's parameters, the panel reporting **resolved** values
is what keeps the change from being a surprise — which is why F4.4 matters more
than it first appears.
"""

from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from ..detail import detail_size
from ..validation import NAMED_SIZES, notice_messages, validate, validate_size


class ImageDetailView(View):
    """Render one image large, with the parameters actually used."""

    http_method_names = ["get", "head", "options"]

    def get(self, request, image_id: int):
        if not 1 <= image_id <= settings.GALLERY_CATALOGUE_SIZE:
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

        # `detail_size` is this page's own parameter, so `validate` — which
        # speaks the gallery's vocabulary — does not see it. It is checked here
        # and its rejection joined to the rest, so a bad value recovers exactly
        # like any other rather than being silently ignored.
        _, detail_rejection = validate_size(
            request.GET.get("detail_size") or None,
            default="large",
            minimum=settings.GALLERY_MIN_DIMENSION,
            maximum=settings.GALLERY_MAX_DIMENSION,
        )
        if detail_rejection is not None:
            result.rejections.append(detail_rejection)

        if not result.is_valid:
            return HttpResponseRedirect(self._corrected_url(request, image_id, result))

        return render(request, "detail.html", self._context(request, image_id, result))

    def _resolve_size(self, request, result) -> str:
        """The size to render at: the user's choice here, or the default.

        Two parameters, deliberately. `size` is the *gallery's* — it arrived on
        the tile link and governs the back link. `detail_size` is a choice made
        on this page, and it wins.

        Keeping them separate is what stops a choice here leaking back into the
        grid: opening one image at `small` must not silently re-render the
        whole gallery on return
        (docs/adr/0007-detail-view-size.md § Amendment).

        With no choice made, the ADR 7 default applies unchanged — arriving
        from a `small` gallery still gives `large`.
        """
        chosen = request.GET.get("detail_size")
        if chosen:
            resolved, rejection = validate_size(
                chosen,
                default="large",
                minimum=settings.GALLERY_MIN_DIMENSION,
                maximum=settings.GALLERY_MAX_DIMENSION,
            )
            if rejection is None:
                return resolved

        return detail_size(result.size, large=settings.GALLERY_SIZE_LARGE)

    def _context(self, request, image_id: int, result) -> dict:
        """Everything the page shows, with the size already resolved.

        The gallery's own size is kept alongside it because the back link has
        to restore what the *gallery* was showing, not what this page chose.
        """
        size = self._resolve_size(request, result)

        return {
            "title": f"Image {image_id}",
            "image_id": image_id,
            # Rendered here rather than by a script: this page is
            # server-rendered, so an explanation that waited for JavaScript
            # would be missing for the moment before it ran.
            "notices": notice_messages(request.GET.getlist("notice")),
            "image_url": self._image_url(image_id, size, result),
            "back_url": self._back_url(result),
            # Resolved values, for the parameters panel (F4.4). These are what
            # the controls are set to as well as what the panel reports — the
            # two cannot disagree because they are the same value.
            "size": size,
            "grayscale": result.grayscale,
            "blur": result.blur,
            "named_sizes": NAMED_SIZES,
            # Empty unless a custom size is active. The select is disabled when
            # it is, so the two controls cannot both submit `detail_size` — the
            # field owns the parameter while it holds a value.
            "custom_size": "" if size in NAMED_SIZES else size,
            "max_blur": settings.GALLERY_MAX_BLUR,
            # The gallery's own state, carried through the form as hidden
            # fields. Submitting the panel must not lose where the user came
            # from: without these, applying a filter here would return them to
            # page 1 of an unfiltered grid.
            "carried": self._carried_state(result),
        }

    def _carried_state(self, result) -> list[tuple[str, str]]:
        """Gallery state the panel's form must preserve.

        Deliberately excludes `detail_size`, which the form's own control
        owns — including it as a hidden field too would submit the parameter
        twice, and the hidden copy would win.
        """
        carried = []
        if result.page != 1:
            carried.append(("page", str(result.page)))
        if result.count != settings.GALLERY_DEFAULT_PAGE_SIZE:
            carried.append(("count", str(result.count)))
        if result.size != settings.GALLERY_DEFAULT_SIZE:
            carried.append(("size", result.size))
        return carried

    def _image_url(self, image_id: int, size: str, result) -> str:
        """The proxy URL for the bytes, built by reversing the route (F5.4).

        Carries the resolved size and the filters as given: the two halves of
        ADR 7's split, expressed in one URL.
        """
        params = {"size": size}
        if result.grayscale:
            params["grayscale"] = "1"
        if result.blur:
            params["blur"] = str(result.blur)

        query = "&".join(f"{name}={value}" for name, value in params.items())
        return f"{reverse('image', args=[image_id])}?{query}"

    def _back_url(self, result) -> str:
        """Back to the gallery, restoring page and filters (F4.1).

        The **gallery's** size, not this page's: returning to a grid rendered
        at `large` when the user left one rendered at `small` would be a change
        they never asked for.

        Defaults are omitted, so a user who changed nothing goes back to a
        clean URL rather than one listing every default.
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

    def _corrected_url(self, request, image_id: int, result) -> str:
        """The same page with invalid values replaced and notices appended."""
        params = request.GET.copy()

        resolved = {
            "page": (result.page, 1),
            "count": (result.count, settings.GALLERY_DEFAULT_PAGE_SIZE),
            "size": (result.size, settings.GALLERY_DEFAULT_SIZE),
            "blur": (result.blur, 0),
        }
        for name, (value, default) in resolved.items():
            if value == default:
                params.pop(name, None)
            else:
                params[name] = str(value)

        if result.grayscale:
            params["grayscale"] = "1"
        else:
            params.pop("grayscale", None)

        # A rejected choice is dropped rather than corrected to a value the
        # user did not pick. Removing it returns the page to its ADR 7 default,
        # which is the honest fallback: they asked for something unavailable,
        # so they get what they would have got without asking.
        if any(r.parameter == "size" for r in result.rejections):
            params.pop("detail_size", None)

        params.setlist("notice", [rejection.notice for rejection in result.rejections])

        return f"{reverse('detail', args=[image_id])}?{params.urlencode()}"
