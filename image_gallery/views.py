"""Views for the image gallery.

Class-based, one concern each, per docs/adr/0013-module-structure.md. The
gallery views arrive with the service layer and move into a `views/` package at
that point; today this module holds the application shell and the health
endpoint.

The behaviour of every endpoint is specified in docs/api-contract.md, and
tests/unit/test_api_contract.py fails if the two diverge.
"""

from django.http import JsonResponse
from django.shortcuts import render
from django.views import View


class AppShellView(View):
    """Serve the application shell.

    The gallery is rendered client-side, so this returns markup and assets
    only; image data arrives from the JSON API.
    """

    http_method_names = ["get", "head", "options"]

    def get(self, request):
        return render(request, "index.html", {"title": "Image Gallery"})


class HealthView(View):
    """Liveness endpoint used by the container health check.

    Deliberately shares nothing with the gallery views: it must keep answering
    when the gallery cannot, so it reads no query parameters and depends on no
    service.
    """

    http_method_names = ["get", "head", "options"]

    def get(self, request):
        return JsonResponse({"status": "ok"})
