"""Django settings for the image gallery.

Deliberately database-free: the application holds no user-owned data and caches
only recomputable URL/metadata payloads, so `DATABASES` is empty and the
contrib apps that require it are not installed.

**This module is the only place the application reads `os.environ`.** Every
environment variable is resolved here into a named module-level setting, and
application code reaches it through `django.conf.settings` rather than reading
the environment itself. That keeps the full configuration surface auditable in
one file and makes settings overridable in tests via `override_settings`.

Two unavoidable exceptions live outside this module, both bootstrap-only:
`wsgi.py` and `manage.py` set `DJANGO_SETTINGS_MODULE`, which is what points
Django at this file in the first place and therefore cannot live inside it.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = _env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves everything under STATIC_ROOT. Must sit directly after the security
    # middleware and before CommonMiddleware, per WhiteNoise's documented order.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "image_gallery.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "image_gallery.wsgi.application"

# No relational store: see README "State model choice and rationale".
DATABASES = {}

GALLERY_CACHE_TTL = _env_int("GALLERY_CACHE_TTL", 300)
GALLERY_CACHE_MAX_ENTRIES = _env_int("GALLERY_CACHE_MAX_ENTRIES", 1000)
GALLERY_CACHE_CULL_FREQUENCY = _env_int("GALLERY_CACHE_CULL_FREQUENCY", 3)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "image-gallery",
        "TIMEOUT": GALLERY_CACHE_TTL,
        "OPTIONS": {
            "MAX_ENTRIES": GALLERY_CACHE_MAX_ENTRIES,
            "CULL_FREQUENCY": GALLERY_CACHE_CULL_FREQUENCY,
        },
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Defaults beside the package so local runs and tests do not depend on a
# platform-specific path; the container overrides it to /var/www/static.
STATIC_ROOT = Path(
    os.environ.get("DJANGO_STATIC_ROOT", BASE_DIR.parent / "staticfiles")
)

# WhiteNoise emits a UserWarning when STATIC_ROOT is missing. The container
# always has it (collectstatic runs at build time), but a fresh checkout does
# not, so create it rather than let every local test run print a warning.
STATIC_ROOT.mkdir(parents=True, exist_ok=True)

# WhiteNoise serves STATIC_ROOT from the application process, so the container
# needs no separate web server.
#
# Manifest storage (content-hashed filenames, far-future caching) requires
# `collectstatic` to have run — without a manifest it raises on every template
# {% static %} tag. The container runs collectstatic at build time; local dev
# and the test suite do not, so the manifest variant is opt-in via env and the
# Dockerfile switches it on.
_static_backend = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
    if _env_bool("DJANGO_STATIC_MANIFEST", False)
    else "whitenoise.storage.CompressedStaticFilesStorage"
)

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": _static_backend,
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Gallery configuration (env-driven; consumed once features land) ---
GALLERY_UPSTREAM_BASE_URL = os.environ.get(
    "GALLERY_UPSTREAM_BASE_URL", "https://picsum.dev"
)
GALLERY_DEFAULT_SIZE = os.environ.get("GALLERY_DEFAULT_SIZE", "medium")
GALLERY_DEFAULT_PAGE_SIZE = _env_int("GALLERY_DEFAULT_PAGE_SIZE", 10)
GALLERY_UPSTREAM_TIMEOUT = float(os.environ.get("GALLERY_UPSTREAM_TIMEOUT", "5.0"))
GALLERY_UPSTREAM_RETRIES = _env_int("GALLERY_UPSTREAM_RETRIES", 2)
GALLERY_UPSTREAM_BACKOFF = float(os.environ.get("GALLERY_UPSTREAM_BACKOFF", "0.2"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "()": "image_gallery.logging.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
}
