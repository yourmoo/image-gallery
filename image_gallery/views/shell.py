"""The application shell, and the document boundary where bad URLs recover.

Under docs/adr/0002-client-side-rendering.md this response carries no image
data — the browser builds the grid. What it does carry is the bounds the client
needs to derive an id range (docs/adr/0020-ids-are-derived-in-the-browser.md)
and the guarantee that those bounds are already valid, which is what lets the
image endpoints stay strict
(docs/adr/0019-validation-errors-carry-a-usable-payload.md).

A pasted or hand-edited URL arrives here as a document request. This view
validates it, applies the fallbacks, and redirects to the corrected address
with a notice, so the client never has a chance to send the bad value onward.
"""

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from ..validation import NAMED_SIZES, validate


class AppShellView(View):
    """Serve the shell, redirecting first if the query string needs correcting."""

    http_method_names = ["get", "head", "options"]

    def get(self, request):
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

        if not result.is_valid:
            return HttpResponseRedirect(self._corrected_url(request, result))

        return render(request, "index.html", self._context(result))

    def _context(self, result) -> dict:
        """What the template needs, and nothing the client could misuse."""
        return {
            "title": "Image Gallery",
            # Bounds, not answers: the client derives its own id range from
            # these. They are configuration, never values the client decides.
            "page": result.page,
            "count": result.count,
            "catalogue_size": settings.GALLERY_CATALOGUE_SIZE,
            # The count control's options. F2.5 requires a real control, and
            # rendering it server-side from the same setting the validator uses
            # means the widget cannot offer a value the server would reject.
            "page_sizes": settings.GALLERY_PAGE_SIZES,
            # The active variations, already validated. `size` also drives
            # `data-size` on the grid, which selects the cell floor
            # (docs/ui/design-system.md) — safe to echo into markup precisely
            # because it has been through the validator, so `?size=huge` can
            # never reach a CSS selector.
            "size": result.size,
            "named_sizes": NAMED_SIZES,
            # The field's value, empty unless a custom size is active. A select
            # cannot show a value it does not list, so the two controls split
            # the job: named sizes in the dropdown, WxH in the field.
            "custom_size": "" if result.size in NAMED_SIZES else result.size,
            "grayscale": result.grayscale,
            "blur": result.blur,
            "max_blur": settings.GALLERY_MAX_BLUR,
        }

    def _corrected_url(self, request, result) -> str:
        """The same URL with invalid values replaced and notices appended.

        **Every validated parameter is written back**, not only the rejected
        ones. The corrected URL has to survive a second pass — the browser
        follows it, this view validates it again, and anything still invalid
        would redirect once more. Writing back the resolved values guarantees
        that second pass is clean, which is the loop this design has to rule
        out.

        A parameter left at its default is dropped rather than spelled out, so
        a corrected URL stays as short as the user's intent: `?size=huge`
        becomes `?notice=invalid_size`, not a full listing of every default.

        Built with `reverse` rather than a literal path, per F5.4, and encoded
        with `QueryDict.urlencode` rather than `urllib`'s: several parameters
        can be invalid at once, so `notice` is a repeated key, and
        `urllib.parse.urlencode` keeps only the last value of a QueryDict even
        with `doseq=True`.
        """
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

        params.setlist("notice", [rejection.notice for rejection in result.rejections])

        return f"{reverse('index')}?{params.urlencode()}"
