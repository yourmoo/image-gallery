"""Liveness endpoint used by the container health check."""

from django.http import JsonResponse
from django.views import View


class HealthView(View):
    """Deliberately shares nothing with the gallery.

    It must keep answering when the gallery cannot, so it reads no query
    parameters, calls no service, and uses no mixin. In particular it does not
    check the upstream image provider: the application is live during an
    upstream outage because it degrades to placeholders rather than failing
    (docs/adr/0012-resilience-strategy.md), and a health check that failed
    there would have an orchestrator restart a container that is working.
    """

    http_method_names = ["get", "head", "options"]

    def get(self, request):
        return JsonResponse({"status": "ok"})
