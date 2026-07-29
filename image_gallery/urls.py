from django.urls import path

from . import views

# Route names are the contract for internal links: templates and tests reverse
# these rather than hardcoding paths (brief line 80). docs/api-contract.md
# documents every route here, and a test fails if the two drift apart.
urlpatterns = [
    path("", views.AppShellView.as_view(), name="index"),
    # Two routes, deliberately distinct. `/images/<id>` is a *page* a user can
    # link to and bookmark; `/img/<id>` is the bytes an <img> element fetches.
    # They were briefly the same path, which meant the detail page and the
    # image it displays could not both exist — see docs/ui/design-system.md,
    # which had the split right from the start.
    path("images/<int:image_id>", views.ImageDetailView.as_view(), name="detail"),
    path("img/<int:image_id>", views.ImageProxyView.as_view(), name="image"),
    path("healthz", views.HealthView.as_view(), name="healthz"),
]
