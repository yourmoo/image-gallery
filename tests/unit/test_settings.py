import ast
from pathlib import Path

from django.conf import settings

import image_gallery

PACKAGE_DIR = Path(image_gallery.__file__).parent

# Bootstrap modules that must set DJANGO_SETTINGS_MODULE before Django can load
# the settings module, and so cannot themselves read it from settings.
ENV_BOOTSTRAP_EXEMPT = {"wsgi.py", "manage.py"}


def _reads_environ(source: str) -> bool:
    """True if the module accesses ``os.environ`` or ``os.getenv``."""
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
            return True

    return False


def test_only_settings_reads_the_environment():
    """Env vars are resolved in settings.py alone; app code uses settings.

    Keeps the whole configuration surface auditable in one file and lets tests
    override values with ``override_settings`` rather than patching os.environ.
    """
    offenders = [
        path.name
        for path in PACKAGE_DIR.rglob("*.py")
        if path.name != "settings.py"
        and path.name not in ENV_BOOTSTRAP_EXEMPT
        and _reads_environ(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_no_database_is_configured():
    """The gallery is deliberately database-free; guard against regressions.

    Django normalises an empty ``DATABASES`` setting by filling in a "dummy"
    backend, so the assertion targets the resolved engine rather than an empty
    dict.
    """
    engines = {db["ENGINE"] for db in settings.DATABASES.values()}

    assert engines <= {"django.db.backends.dummy"}


def test_cache_is_configured_with_bounds():
    cache = settings.CACHES["default"]

    assert cache["BACKEND"].endswith("LocMemCache")
    assert cache["OPTIONS"]["MAX_ENTRIES"] > 0


def test_cache_settings_are_named_and_wired_into_caches():
    """Cache tuning is reachable as settings, not buried in the CACHES dict."""
    cache = settings.CACHES["default"]

    assert cache["TIMEOUT"] == settings.GALLERY_CACHE_TTL
    assert cache["OPTIONS"]["MAX_ENTRIES"] == settings.GALLERY_CACHE_MAX_ENTRIES
    assert cache["OPTIONS"]["CULL_FREQUENCY"] == settings.GALLERY_CACHE_CULL_FREQUENCY


def test_gallery_defaults_are_present():
    assert settings.GALLERY_DEFAULT_PAGE_SIZE == 10
    assert settings.GALLERY_UPSTREAM_BASE_URL.startswith("http")
