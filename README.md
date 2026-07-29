# Image Gallery — Baseline

Django application scaffold for the picsum.dev image gallery take-home.

**Status:** this is the *baseline harness only* — Django, pytest, pytest-bdd,
Playwright, and Docker are set up and verified. The gallery features described
in `django_image_gallery_assignment.md` (grid, pagination, transformations,
detail view, upstream integration, caching) are **not implemented yet**.

## Prerequisites

- Python 3.12+
- Docker with Compose v2 (for the containerised run)

## Layout

```text
image_gallery/          application package (templates + static ship inside it)
  settings.py           env-driven configuration
  urls.py, views.py     landing page + /healthz
  manage.py             console entry point -> `image-gallery-admin`
tests/                  all test code and test config -> see tests/README.md
docs/                   longer-form documentation -> see docs/README.md
Dockerfile              two-stage: builds a wheel, runtime installs it only
compose.yaml            single-command run, host port 8080 -> gunicorn 8000
```

## Build

Local development install:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Container image:

```powershell
docker compose build
```

## Run

```powershell
docker compose up -d
```

Then open <http://localhost:8080>. Health endpoint: <http://localhost:8080/healthz>.

Stop with `docker compose down`.

### The same image, two upstreams

The upstream provider is an environment variable, never baked into the image
([ADR 8](docs/adr/0008-configuration-in-settings.md)), so one artifact serves
both purposes and they run side by side:

| | Command | Upstream | Shows |
| --- | --- | --- | --- |
| **Demo** | `docker compose up -d` | picsum.dev | Real photographs, on 8080 |
| **Testing** | `docker compose -f compose.e2e.yaml up -d` | a fake in its own container | A 1×1 placeholder, on 8081 |

The test stack's images are deliberately blank: the scenarios assert on the
dimensions and filters the application *requested upstream*, never on pixels,
so real photographs would only make the suite slower.

Each file declares its own `name:`, which is what keeps them apart. Compose
otherwise derives the project from the directory, and since both declare a
service called `web` they would resolve to the same container — starting one
would replace the other, and tearing either down would stop both.

For a local (non-container) server:

```powershell
.\.venv\Scripts\image-gallery-admin.exe runserver
```

## Test

All testing documentation — commands, coverage, what is covered, and what is
out of scope — lives in **[tests/README.md](tests/README.md)**.

## Configuration

All settings are environment-driven; defaults are in `compose.yaml`.

`image_gallery/settings.py` is the **only** module that reads `os.environ`.
Every variable below is resolved there into a named setting, and application
code reaches it through `django.conf.settings`. The single exception is
`DJANGO_SETTINGS_MODULE`, set in `wsgi.py` and `manage.py` because it is what
points Django at the settings module in the first place. A unit test enforces
this — see `test_only_settings_reads_the_environment`.

| Variable | Setting | Default | Purpose |
| --- | --- | --- | --- |
| `DJANGO_DEBUG` | `DEBUG` | `false` | Django debug mode |
| `DJANGO_ALLOWED_HOSTS` | `ALLOWED_HOSTS` | `*` | Comma-separated allowed hosts |
| `DJANGO_SECRET_KEY` | `SECRET_KEY` | dev placeholder | Override in any real deployment |
| `DJANGO_LOG_LEVEL` | `LOGGING` root level | `INFO` | Root log level |
| `DJANGO_STATIC_ROOT` | `STATIC_ROOT` | `./staticfiles` | collectstatic target |
| `DJANGO_STATIC_MANIFEST` | `STORAGES` staticfiles backend | `false` | Content-hashed filenames; needs collectstatic, so the container enables it |
| `GALLERY_CACHE_TTL` | `GALLERY_CACHE_TTL` | `300` | Cache entry TTL (seconds) |
| `GALLERY_CACHE_MAX_ENTRIES` | `GALLERY_CACHE_MAX_ENTRIES` | `1000` | Cache entry ceiling |
| `GALLERY_CACHE_CULL_FREQUENCY` | `GALLERY_CACHE_CULL_FREQUENCY` | `3` | Fraction culled when full |
| `GALLERY_DEFAULT_SIZE` | `GALLERY_DEFAULT_SIZE` | `medium` | Default named image size |
| `GALLERY_DEFAULT_PAGE_SIZE` | `GALLERY_DEFAULT_PAGE_SIZE` | `10` | Images per page |
| `GALLERY_UPSTREAM_BASE_URL` | `GALLERY_UPSTREAM_BASE_URL` | `https://picsum.dev` | Provider base URL |
| `GALLERY_UPSTREAM_TIMEOUT` | `GALLERY_UPSTREAM_TIMEOUT` | `5.0` | Per-request timeout (seconds) |
| `GALLERY_UPSTREAM_RETRIES` | `GALLERY_UPSTREAM_RETRIES` | `2` | Retry attempts on transient failure |
| `GALLERY_UPSTREAM_BACKOFF` | `GALLERY_UPSTREAM_BACKOFF` | `0.2` | Retry backoff base (seconds) |

`E2E_BASE_URL` is deliberately **not** here — it is a test-harness knob read by
`tests/conftest.py` to tell Playwright which server to drive. The application
never reads it, so it stays out of the shipped settings.

## Design decisions so far

**No database.** The application owns no persistent user data — all state is
either URL-driven or fetched from picsum.dev, and the brief scopes caching to
the process lifetime. `DATABASES` is therefore empty and `admin`/`auth`/
`sessions` are not installed. Note that Django normalises an empty `DATABASES`
into a `dummy` backend entry; the guard test asserts on that engine.

**LocMemCache, bounded.** Only metadata/URL payloads are cached, not image
bytes, so the working set is small. `MAX_ENTRIES` plus `CULL_FREQUENCY` gives
LRU-style eviction without adding an external service, which the brief forbids.
Trade-off: the cache is per-process and gunicorn runs 2 workers, so hit rates
are per-worker.

**Wheel-based container.** The build stage produces a wheel; the runtime stage
installs only that, so the shipped image carries no source tree and no build
tools. `image-gallery-admin` replaces `manage.py` inside the container, and the
process runs as a non-root user.

**WhiteNoise for static files.** Django's staticfiles handler only serves assets
when `DEBUG` is on, so with `DEBUG=false` the container returned 404 for every
asset and rendered unstyled. WhiteNoise serves `STATIC_ROOT` from the gunicorn
process, which keeps the deployment to a single container — the brief rules out
adding external services, so a separate nginx tier was not an option.

**JSON logging via a formatter class.** A `format` string cannot escape quotes
or newlines appearing in log messages, so any such message would emit
unparseable output. `image_gallery/logging.py` serialises through `json.dumps`
instead and merges anything passed as `extra=` into the object, which is what
makes upstream request/response context loggable once the provider exists.

Testing strategy and its rationale are documented in
[tests/README.md](tests/README.md).

## Known upstream behaviour

**picsum.dev occasionally returns the same photograph for two different seeds.**
Measured on 2026-07-29: seeds 8 and 13 return byte-identical responses, and
across seeds 1–30 there are 29 distinct images rather than 30.

This is the provider's behaviour, not a defect in this application. Verified by
requesting picsum directly, bypassing the proxy entirely:

```console
$ curl -s "https://picsum.dev/400/400?seed=8"  | sha256sum
7da0e94959d87a63...
$ curl -s "https://picsum.dev/400/400?seed=13" | sha256sum
7da0e94959d87a63...
```

Two consequences worth knowing:

- **The gallery shows what upstream returns.** Image 8 and image 13 are
  distinct entries with their own ids, URLs, detail pages, and cache keys; they
  simply happen to render the same photograph. Nothing here dedupes them —
  doing so would mean the application deciding a page has nine images when the
  catalogue says ten.
- **It does not affect determinism.** A given seed always returns the same
  bytes, which is what pagination and bookmarking rely on ([ADR 9](docs/adr/0009-url-vocabularies.md)).
  The collision is between *different* seeds, not within one.

If a deployment needed the collision gone, the fix belongs in `provider.py` —
the id-to-seed translation is the only place that decides what upstream is
asked for — by mapping ids onto a seed space known to be collision-free. That
is provider-specific knowledge, which is exactly the kind of thing that module
exists to hold.

## Future work

The Core Requirements of the brief are implemented and covered by scenarios.
What remains is optional rather than outstanding:

- **`/api/images/<id>`** is specified in [the API contract](docs/api-contract.md)
  and not yet routed. Nothing needs it — the detail page renders server-side —
  so it is a public JSON surface waiting for a consumer.
- **Single-flight upstream fetches.** Concurrent misses on a cold key each
  fetch, measured at 5× duplicate requests
  ([ADR 14](docs/adr/0014-concurrency-validation.md)). Accepted, not fixed.
- **The `--image-*` tokens** are ambiguous under custom `WxH` sizes; the grid
  falls back to `--cell-medium` and the served dimensions govern.
