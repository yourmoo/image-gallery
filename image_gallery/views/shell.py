"""The application shell, and the document boundary where bad URLs recover.

Under docs/adr/0002-client-side-rendering.md this response carries no image
data — the browser fetches that from the JSON API. What it does carry is the
guarantee that the client boots with valid parameters, which is what lets the
API stay strict (docs/adr/0019-validation-errors-carry-a-usable-payload.md).

A pasted or hand-edited URL arrives here as a document request. This view
validates it, applies the fallbacks, and redirects to the corrected address
with a notice, so the client never has a chance to send the bad value onward.
"""

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from ..validation import validate


class AppShellView(View):
    """Serve the shell, redirecting first if the query string needs correcting."""

    http_method_names = ["get", "head", "options"]

    def get(self, request):
        result = validate(
            request.GET,
            page_sizes=settings.GALLERY_PAGE_SIZES,
            default_count=settings.GALLERY_DEFAULT_PAGE_SIZE,
            catalogue_size=settings.GALLERY_CATALOGUE_SIZE,
        )

        if not result.is_valid:
            return HttpResponseRedirect(self._corrected_url(request, result))

        return render(
            request,
            "index.html",
            {
                "title": "Image Gallery",
                # The client derives its own id range, so it is handed the
                # bounds rather than the answer
                # (docs/adr/0020-ids-are-derived-in-the-browser.md). These are
                # configuration, never values the client decides.
                "page": result.page,
                "count": result.count,
                "catalogue_size": settings.GALLERY_CATALOGUE_SIZE,
                # Drives `data-size` on the grid, which selects the cell floor
                # (docs/ui/design-system.md). Always the configured default in
                # stage 1: `size` is not validated until the variation stages,
                # and echoing an unvalidated query value into the markup would
                # let `?size=huge` select a cell width.
                "size": settings.GALLERY_DEFAULT_SIZE,
            },
        )

    def _corrected_url(self, request, result) -> str:
        """The same URL with invalid values replaced and a notice appended.

        Parameters this stage does not yet validate are carried through
        untouched rather than dropped: a redirect that discarded `?size=` would
        lose a valid parameter while correcting an unrelated one, which is the
        opposite of "one bad parameter does not discard the good ones"
        (docs/adr/0006-recover-and-explain.md).

        Built with `reverse` rather than a literal path, per F5.4.

        Encoded with `QueryDict.urlencode` rather than `urllib`'s: several
        parameters can be invalid at once, so `notice` is a repeated key, and
        `urllib.parse.urlencode` keeps only the last value of a QueryDict even
        with `doseq=True`.
        """
        params = request.GET.copy()
        params["page"] = str(result.page)
        params["count"] = str(result.count)
        params.setlist("notice", [r.notice for r in result.rejections])

        return f"{reverse('index')}?{params.urlencode()}"
