from django.http import JsonResponse
from django.shortcuts import render


def index(request):
    """Placeholder landing page. Gallery features are not implemented yet."""
    return render(request, "index.html", {"title": "Image Gallery"})


def healthz(request):
    """Liveness endpoint used by the container health check."""
    return JsonResponse({"status": "ok"})
