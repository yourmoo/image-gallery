# Image Gallery

A Django proxy and gallery for picsum.dev images: a paginated grid, size and
filter controls, a detail view, and a shared cache of the image bytes.

**Status:** complete. Every Core Requirement in
`django_image_gallery_assignment.md` is implemented and covered by scenarios —
grid, pagination, transformations, detail view, upstream integration, and
caching. The behavioural suite runs 95 Gherkin cases (59 scenarios, several of
them outlines) through a real browser against the production container image;
see [tests/README.md](tests/README.md).

## Prerequisites

- Python 3.12+
- Docker with Compose v2 (for the containerised run)

## Layout

```text
image_gallery/          application package (templates + static ship inside it)
  settings.py           env-driven configuration; the only reader of os.environ
  urls.py               every route, named -- links reverse these, never paths
  views/                one class per file
    shell.py            /            the gallery shell
    detail.py           /images/<id> the detail shell
    api_image.py        /api/images/<id>  what the detail shell fetches
    image.py            /img/<id>    the image bytes, proxied
    health.py           /healthz
  provider.py           the only module that knows picsum.dev exists
  cache.py              image bytes, with freshness and retention as two windows
  validation.py         the parameter grammar, and what to do with a bad value
  gallery.py, detail.py the page and size rules, as pure functions
  middleware.py         request logging, and the exception boundary
  logging.py            the JSON formatter
  static/js/            derive.js and detail-render.js are pure and unit-tested;
                        gallery.js and detail-panel.js do the DOM
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
| `DJANGO_LOG_LEVEL` | `LOGGING` root level | `INFO` | Django's own log level |
| `DJANGO_STATIC_ROOT` | `STATIC_ROOT` | `./staticfiles` | collectstatic target |
| `DJANGO_STATIC_MANIFEST` | `STORAGES` staticfiles backend | `false` | Content-hashed filenames; needs collectstatic, so the container enables it |
| `GALLERY_LOG_LEVEL` | `gallery.*` logger level | `INFO` | This application's logs, independent of Django's. `DEBUG` adds cache hit/miss per lookup |
| `GALLERY_CACHE_TTL` | `GALLERY_CACHE_TTL` | `3600` | How long a cached image is *preferred* over a refetch |
| `GALLERY_CACHE_RETENTION` | `GALLERY_CACHE_RETENTION` | `86400` | How long it stays available as a stale fallback. **Must exceed the TTL** — enforced by a test |
| `GALLERY_BROWSER_CACHE_MAX_AGE` | `Cache-Control: max-age` | `604800` | How long a browser may keep an image. `0` sends `no-store` |
| `GALLERY_CACHE_MAX_ENTRIES` | `GALLERY_CACHE_MAX_ENTRIES` | `300` | Entry ceiling — a byte budget in disguise |
| `GALLERY_CACHE_CULL_FREQUENCY` | `GALLERY_CACHE_CULL_FREQUENCY` | `3` | Fraction culled when full |
| `GALLERY_CACHE_DIR` | `CACHES` location | `./.gallery-cache` | Where the bytes live; a tmpfs mount in the container |
| `GALLERY_CATALOGUE_SIZE` | `GALLERY_CATALOGUE_SIZE` | `100` | Where the collection ends, so there is a real last page |
| `GALLERY_DEFAULT_SIZE` | `GALLERY_DEFAULT_SIZE` | `medium` | Default named image size |
| `GALLERY_DEFAULT_PAGE_SIZE` | `GALLERY_DEFAULT_PAGE_SIZE` | `10` | Images per page |
| `GALLERY_PAGE_SIZES` | `GALLERY_PAGE_SIZES` | `10,20,50` | What the count control offers, and all the validator accepts |
| `GALLERY_SIZE_SMALL` | `GALLERY_SIZE_SMALL` | `200x200` | Pixels behind the name |
| `GALLERY_SIZE_MEDIUM` | `GALLERY_SIZE_MEDIUM` | `400x400` | Pixels behind the name |
| `GALLERY_SIZE_LARGE` | `GALLERY_SIZE_LARGE` | `800x800` | Pixels behind the name, and the detail view's floor |
| `GALLERY_MIN_DIMENSION` | `GALLERY_MIN_DIMENSION` | `16` | Floor for a custom `WxH` |
| `GALLERY_MAX_DIMENSION` | `GALLERY_MAX_DIMENSION` | `1600` | Ceiling for a custom `WxH`. The provider enforces nothing, so this is what bounds upstream traffic |
| `GALLERY_MAX_BLUR` | `GALLERY_MAX_BLUR` | `10` | Blur ceiling |
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

**The application proxies the image bytes**, so the browser never contacts
picsum.dev and this application actually downloads what it is required to cache
([ADR 3](docs/adr/0003-django-as-image-proxy.md)). Every `<img>` points at
`/img/<id>`.

**A file-backed cache in shared memory.** `FileBasedCache` over a tmpfs mount,
so the "files" never touch a disk and every gunicorn worker reads the same
ones. An earlier `LocMemCache` lived in one process's heap, which made a hit
depend on which of the two workers served the request
([ADR 18](docs/adr/0018-shared-cache-in-shared-memory.md)). Bytes are stored
raw; base64 would inflate every entry by a third for nothing.

`MAX_ENTRIES` is a byte budget in disguise — the backend counts entries, but
the entries here are images, so the cap is a memory decision
([ADR 11](docs/adr/0011-cache-sizing.md)).

**Freshness and retention are two windows.** TTL is how long a cached image is
*preferred*; retention is how long it stays available as a fallback when
upstream fails. Django's cache API cannot return an expired entry, so the
backend timeout is retention and freshness is compared against a stored
timestamp ([ADR 12](docs/adr/0012-resilience-strategy.md)).

**Images are immutable, and cached accordingly.** A given seed and size return
byte-identical bytes, so `/img/<id>` is served
`Cache-Control: public, max-age=604800, immutable` and a reload costs zero
requests rather than one per tile. Placeholders are exempt and answer
`no-store`: they describe one bad moment upstream, not the image, and caching
one would leave a tile broken long after upstream recovered.

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
unparseable output — a traceback most of all. `image_gallery/logging.py`
serialises through `json.dumps` instead and merges anything passed as `extra=`
into the object, so every line stays one parseable record.

**One middleware logs both ends of a request and catches every exception.**
Gunicorn's access log was removed: with one request per tile it produced fifty
lines per page load and said nothing useful. What replaced it carries a
correlating request id, which cache tier answered, and the upstream URL with
its byte count and duration.

The catch is `process_exception`, not a `try` around the view — Django turns an
exception into a response *inside* `get_response`, so by the time an outer
`except` sees anything the debug traceback page has already been built.
Hooking earlier means **no traceback can reach a browser even with
`DEBUG=True`**, which makes it a property of the code rather than of an
environment variable ([ADR 21](docs/adr/0021-observability-and-the-exception-boundary.md)).

**Both pages are shells; the browser builds the DOM.** The gallery derives its
grid from bounds the shell publishes
([ADR 20](docs/adr/0020-ids-are-derived-in-the-browser.md)), and the detail page
fetches `/api/images/<id>`
([ADR 22](docs/adr/0022-the-detail-page-joins-the-client.md)). A rejected
parameter is answered in that payload — the fallback applied, a notice
explaining it — rather than by a redirect.

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

- **Single-flight upstream fetches.** Concurrent misses on a cold key each
  fetch, measured at 5× duplicate requests
  ([ADR 14](docs/adr/0014-concurrency-validation.md)). Accepted, not fixed.
- **One copy of the notice wording remains in JavaScript.** The detail page
  takes its sentences from the server, where they can quote configured bounds;
  the gallery still builds its own from `?notice=` tokens in `derive.js`,
  because it has no payload to read them from. Closing that means giving the
  gallery a payload too
  ([ADR 22](docs/adr/0022-the-detail-page-joins-the-client.md)).
- **The `--image-*` tokens** are ambiguous under custom `WxH` sizes; the grid
  falls back to `--cell-medium` and the served dimensions govern.
