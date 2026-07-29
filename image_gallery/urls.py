from django.urls import path

from . import views

# Route names are the contract for internal links: templates and tests reverse
# these rather than hardcoding paths (brief line 80). docs/api-contract.md
# documents every route here, and a test fails if the two drift apart.
urlpatterns = [
    path("", views.AppShellView.as_view(), name="index"),
    path("images/<int:image_id>", views.ImageProxyView.as_view(), name="image"),
    path("healthz", views.HealthView.as_view(), name="healthz"),
]
