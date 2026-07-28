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

    assert cache["OPTIONS"]["MAX_ENTRIES"] == settings.GALLERY_CACHE_MAX_ENTRIES
    assert cache["OPTIONS"]["CULL_FREQUENCY"] == settings.GALLERY_CACHE_CULL_FREQUENCY


def test_cache_timeout_is_retention_not_ttl():
    """Entries must outlive freshness so they survive as a stale fallback.

    Django's cache cannot return an expired entry, so the backend timeout is
    the retention window and freshness is compared in code.
    See docs/adr/0012-resilience-strategy.md.
    """
    assert settings.CACHES["default"]["TIMEOUT"] == settings.GALLERY_CACHE_RETENTION


def test_retention_outlives_freshness():
    """Retention shorter than TTL would make the stale tier unreachable.

    An entry would expire out of the cache before it could ever be considered
    stale, so the upstream-failure fallback could never fire.
    """
    assert settings.GALLERY_CACHE_RETENTION > settings.GALLERY_CACHE_TTL


def test_gallery_defaults_are_present():
    assert settings.GALLERY_DEFAULT_PAGE_SIZE == 10
    assert settings.GALLERY_UPSTREAM_BASE_URL.startswith("http")
    assert settings.GALLERY_CATALOGUE_SIZE > 0


def test_named_sizes_are_configured_as_dimensions():
    """Named sizes resolve to pixel dimensions in settings, not in code.

    Lets a deployment retune what "large" means; see
    docs/adr/0010-configurable-and-custom-sizes.md.
    """
    named = [
        settings.GALLERY_SIZE_SMALL,
        settings.GALLERY_SIZE_MEDIUM,
        settings.GALLERY_SIZE_LARGE,
    ]

    for value in named:
        width, _, height = value.partition("x")
        assert width.isdigit() and height.isdigit(), f"{value!r} is not WxH"


def test_named_sizes_are_within_the_dimension_bounds():
    """A misconfigured named size must not silently exceed the ceiling.

    Without this the bound would only constrain custom dimensions, leaving
    GALLERY_SIZE_LARGE=5000x5000 free to bypass it entirely.
    """
    low, high = settings.GALLERY_MIN_DIMENSION, settings.GALLERY_MAX_DIMENSION

    for value in (
        settings.GALLERY_SIZE_SMALL,
        settings.GALLERY_SIZE_MEDIUM,
        settings.GALLERY_SIZE_LARGE,
    ):
        for edge in (int(n) for n in value.split("x")):
            assert low <= edge <= high, f"{value!r} outside {low}-{high}"


def test_no_server_side_fetch_concurrency_setting():
    """Django does not fan out, so there is no thread pool to size.

    Each image is fetched by its own /images/<id> request; parallelism is the
    browser's connection pool. A reinstated GALLERY_FETCH_CONCURRENCY would mean
    server-side fan-out had crept back in — see
    docs/adr/0017-image-fetch-timing.md.
    """
    assert not hasattr(settings, "GALLERY_FETCH_CONCURRENCY")


def test_cache_cap_bounds_worker_memory():
    """The entry cap is a byte budget in disguise; keep it defensibly small.

    At ~182 KB per entry (the measured median at GALLERY_MAX_DIMENSION), 300
    entries is ~55 MB per worker. See docs/adr/0011-cache-sizing.md.
    """
    ceiling_entry_bytes = 182_000
    budget_bytes = 64 * 1024 * 1024

    worst_case = settings.GALLERY_CACHE_MAX_ENTRIES * ceiling_entry_bytes

    assert worst_case <= budget_bytes
