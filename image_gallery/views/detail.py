"""`/images/<id>` — the detail page's shell.

A **page**, not bytes: `/img/<id>` serves those. Two routes because a user
links to and bookmarks the first while an `<img>` element fetches the second,
and a single path cannot be both.

**This view renders no content.** It serves markup and a script; the script
fetches `/api/images/<id>` and builds the page from the payload
(docs/adr/0022-the-detail-page-joins-the-client.md). The gallery already worked
this way, so the application now has one rendering model instead of two.

What is left here is the one thing the client cannot do for itself: **refuse an
id outside the catalogue**. The id is in the path, so it is known before any
script runs, and a document that 404s is what a bookmark, a crawler, and a
`curl` all need to see. A bad *parameter* is different — it has a sensible
substitute, so the API applies the fallback and explains it, and the page
answers 200 (docs/adr/0006-recover-and-explain.md).

Nothing redirects. The requirement is that a user who asks for something
unavailable is recovered and told, which the payload does in one response — it
never asked for a `3xx`. Removing the redirect also removed a class of bug: two
parameters fed the size, the correction dropped only one of them, and the page
redirected to itself until the browser gave up.
"""

from __future__ import annotations

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views import View


class ImageDetailView(View):
    """Serve the detail shell, or refuse an id that cannot exist."""

    http_method_names = ["get", "head", "options"]

    def get(self, request, image_id: int):
        if not 1 <= image_id <= settings.GALLERY_CATALOGUE_SIZE:
            raise Http404(f"no image {image_id}")

        # The id is all the template needs: it titles the page, and the script
        # reads it back to know which image to ask about. Everything else —
        # resolved size, filters, notices, the back link — is the payload's.
        return render(request, "detail.html", {"image_id": image_id})
