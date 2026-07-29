# Tests

All test code and test configuration live in this directory.

```text
tests/
  README.md             this guide — the single source for testing docs
  pytest.ini            pytest configuration (rootdir when passed via -c)
  .coveragerc           coverage configuration
  conftest.py           shared fixtures
  cucumber_html.py      renders Cucumber JSON to a readable scenario report
  unit/                 module tests and JSON API tests, in-process
  features/             Gherkin .feature files — the behavioural spec
  e2e/                  step definitions and fixtures, Playwright (marked `e2e`)
    conftest.py         stack fixtures, fake-upstream client, shared steps
    fake_upstream/      the picsum.dev stand-in and its Dockerfile
  reports/              generated coverage and report output (gitignored)
```

The stack the behavioural tier runs against is defined in `compose.e2e.yaml` at
the project root, next to the `compose.yaml` used for ordinary deployment.

Because the configuration is not at the project root, **every command must pass
`-c tests/pytest.ini`**. Run them from the project root.

A bare `pytest` with no `-c` still collects and runs, but silently without the
markers, BDD feature path, and Django settings — so always include the flag.

## Strategy

Two tiers, with **different measures of completeness**. See
[ADR 15](../docs/adr/0015-test-strategy.md).

| Tier | Verifies | Measured by | Runs against |
| --- | --- | --- | --- |
| `unit/` | Modules in isolation, and the JSON API | **Coverage ≥70%** | Imported code, Django test client |
| `e2e/` | All Gherkin scenarios | **Every scenario bound** | A real browser and a running container |

**Every `.feature` scenario runs in `e2e/`, without exception** — including
`health.feature`, which could run in-process. One tier means one scenario
report and one place to look.

The gallery is client-side rendered ([ADR 2](../docs/adr/0002-client-side-rendering.md)),
so the Django test client cannot verify gallery behaviour — it does not execute
JavaScript and would only ever see an empty application shell. Behavioural
scenarios therefore run in a browser.

**Coverage is a unit-test measure, deliberately.** Browser tests exercise Django
inside a container the in-process coverage tool cannot observe, so `unit/`
carries the 70% gate alone. That is the right place for it: the service modules
`validation.py`, `provider.py`, `cache.py`, and `gallery.py` — planned in
[ADR 13](../docs/adr/0013-module-structure.md), not yet written — will be pure
or near-pure and are more precisely tested directly than inferred through a
browser. The JSON API is tested here too, through the Django test client:
request and response assertions need no browser.

**Gherkin completeness is the behavioural measure.** A coverage percentage says
nothing about whether pagination was exercised. The equivalent guarantee is that
every scenario in `features/` is bound to a step definition:

```powershell
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini `
  --generate-missing --feature tests/features
```

This names every unbound scenario with its file and line. It is a CI gate: a
specification that silently goes unimplemented fails the build.

**When adding a test, prefer the tier that can actually catch the bug.**
Validation rules, URL translation, and cache tiering belong in `unit/`. Anything
the user sees belongs in a scenario.

## Prerequisites

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m playwright install chromium
```

The last line is only needed for the end-to-end tests.

## Unit tests

### How unit tests work

In-process: pytest imports the code and calls it directly. No server, no
browser, no container — which is why the whole tier runs in about two seconds
and can be left running while editing.

`pytest-django` supplies the settings, so anything reading `django.conf.settings`
behaves as it would in the application. `DJANGO_SETTINGS_MODULE` is set in
`pytest.ini`, not in each test.

What lives here:

| Kind | Example | Why here rather than a scenario |
| --- | --- | --- |
| Settings and configuration | `test_settings.py` | Asserts the shape of `CACHES`, `DATABASES`, and the env-var contract — invisible from a browser |
| Documented contracts | `test_api_contract.py` | Fails when `docs/api-contract.md` and the routes disagree |
| Harness integrity | `test_bdd_harness.py`, `test_requirement_coverage.py` | Guard the test suite itself — a renamed scenario, an untagged requirement |
| The JSON API | through the Django test client | Request and response assertions need no JavaScript |
| Pure logic | validation, URL translation, cache tiering | More precisely tested directly than inferred through a page |

Two of these are worth calling out because they test the tests:

- `test_requirement_coverage.py` fails if a requirement in
  `docs/core-features.md` has no scenario, if a scenario names a requirement
  that does not exist, or if a scenario carries no build stage.
- `test_bdd_harness.py` fails if the cold-cache list in `e2e/conftest.py` names
  a scenario that has been renamed — a coupling that would otherwise break
  silently and let a cache scenario run against a warm cache.

### Running them

The `-m "not e2e"` filter deselects the browser tests, leaving the unit and BDD
suites:

```powershell
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini -m "not e2e"
```

With coverage, enforcing the 70% gate:

```powershell
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini -m "not e2e" `
  --cov --cov-config=tests/.coveragerc --cov-report=term-missing
```

Add `--cov-report=html:tests/reports/htmlcov` for a browsable report.

Coverage writes its raw database to `tests/reports/.coverage`. That path is set
by `data_file` in `.coveragerc`; without it, coverage drops a `.coverage` file
in whatever directory you ran from. Everything under `tests/reports/` is a
generated artifact and is gitignored — safe to delete at any time.

## Behavioural tests

The Playwright tests drive a real browser against a **running stack**, so start
one first. This is where every Gherkin scenario runs.

Alongside the scenarios, this tier keeps a few deployment checks that only a
real browser can make:

- Every subresource the page requests returns below 400
- Declared assets resolve and have the right content type
- An `<img>` served by the proxy endpoint actually renders

### How behavioural tests work

A `.feature` file is the specification; a step definition is the code that makes
one Gherkin line executable. `pytest-bdd` matches them by text, so this line:

```gherkin
Then the page shows images 11 to 20
```

runs the function decorated with
`@then(parsers.parse("the page shows images {first:d} to {last:d}"))`.

**Steps drive the browser, never the code.** No step imports Django,
instantiates a view, or uses the test client — the application is a black box
reached over HTTP. That is what keeps a scenario honest about what a user can
actually observe. The single exception is the fake upstream's request log,
described above, which answers questions the browser cannot.

Where the code lives:

| File | Holds |
| --- | --- |
| `e2e/conftest.py` | The stack fixtures, the fake-upstream client, and every step used by more than one feature file |
| `e2e/test_gallery_steps.py` | Steps unique to `gallery.feature` |
| `e2e/test_variations_steps.py` | Steps unique to `variations.feature` |
| `e2e/test_detail_steps.py` | Steps unique to `detail.feature` |
| `e2e/test_health_steps.py` | Steps for `health.feature` |

Shared steps sit in `conftest.py` because pytest-bdd resolves step definitions
from there across every feature file — one definition of "the response status is
200" rather than four that can drift apart.

**Elements are found by `data-testid`, never by CSS class**, so restyling cannot
break a test. The hooks each module expects are listed in its docstring, and
they are a contract: the templates have to provide them.

**Scenario isolation.** An autouse fixture resets the fake's request log and
faults before every scenario. Three scenarios also need an empty image cache —
they are listed in `COLD_CACHE_SCENARIOS`, and the cache directory is emptied
for those alone rather than restarting the container.

### The stack

`compose.e2e.yaml` runs two services, and the suite starts them itself if they
are not already up:

```powershell
docker compose -f compose.e2e.yaml up -d --build
$env:E2E_BASE_URL = 'http://127.0.0.1:8081'
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini -m e2e --no-cov
docker compose -f compose.e2e.yaml down -v
```

| Service | Port | What it is |
| --- | --- | --- |
| `web` | 8081 | The **production image**, built from the shipping `Dockerfile` |
| `fake-upstream` | 8091 | A stand-in for picsum.dev, with a control API |

**`web` is the real image, not a development server.** It runs gunicorn with the
same worker model that ships, which matters because each worker holds part of
the picture: the cache is shared through a tmpfs mount
([ADR 18](../docs/adr/0018-shared-cache-in-shared-memory.md)), and a harness
running a single `runserver` process could not observe whether that sharing
works.

**`fake-upstream` replaces picsum.dev** so scenarios are deterministic and
offline. It serves the upstream vocabulary from
[ADR 9](../docs/adr/0009-url-vocabularies.md) —
`/{width}/{height}?seed=N&grayscale=1&blur=M` — records every request, and
injects faults on demand. Steps drive it over HTTP:

| Endpoint | Purpose |
| --- | --- |
| `POST /_control/faults` | Fail specific seeds, take the upstream down, or hang past the timeout |
| `GET /_control/requests` | Every request the application made, with parsed parameters |
| `POST /_control/reset` | Clear the log and all faults — runs before every scenario |

That control surface lives only on the fake. The application image carries no
test scaffolding, which is what the project's SOLID and 12-factor guardrails
require.

`GET /_control/requests` is also the only way several scenarios can be asserted
at all: "no upstream image requests are made" is a claim about what Django did,
and the browser cannot see that.

Point the suite at a different target with `E2E_BASE_URL` — useful against a
local `image-gallery-admin runserver`, though the cache and worker behaviour
will not match the container.

Useful Playwright flags: `--headed` to watch the browser, `--slowmo=500` to slow
it down, `--browser firefox` to switch engine (install it first with
`playwright install firefox`).

## Everything at once

Requires the stack, since the e2e tests are included:

```powershell
docker compose -f compose.e2e.yaml up -d --build
$env:E2E_BASE_URL = 'http://127.0.0.1:8081'
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini
```

Expect this to take several minutes — the behavioural tier drives a real browser
through 81 scenarios, and most of them currently fail while waiting for elements
that do not exist yet.

## Reports

All artifacts land in `tests/reports/`, which is gitignored.

**Where to look, by question:**

| Question | Open |
| --- | --- |
| Which scenarios passed or failed? | `tests/reports/e2e/scenarios.html` |
| Why did that scenario fail — which step? | `tests/reports/e2e/scenarios.html` (errors inline) |
| What is the coverage percentage? | terminal, or `tests/reports/unit/htmlcov/index.html` |
| Which lines are uncovered? | `tests/reports/unit/htmlcov/index.html` |
| Which unit tests ran? | `tests/reports/unit/report.html` |
| Scenario results for a CI tool | `tests/reports/e2e/cucumber.json` |

Paths are relative to the project root, so from a terminal there:

```powershell
start tests\reports\e2e\scenarios.html
start tests\reports\unit\htmlcov\index.html
```

**The two tiers report separately, into separate directories.** They measure
different things ([ADR 15](../docs/adr/0015-test-strategy.md)) — the unit tier
is measured by coverage, the behavioural tier by scenarios passing — so merging
them into one report would blur both.

```text
tests/reports/
  unit/
    report.html          test results
    htmlcov/index.html   coverage, browsable
  e2e/
    report.html          test results
    scenarios.html       Given/When/Then, browsable
    cucumber.json        scenario-level results, machine-readable
```

Each tier's command writes only its own directory. Running the e2e command
produces no coverage report, and the unit command produces no Cucumber report —
expected, not a misconfiguration.

### Unit tier

Results plus browsable coverage, into `tests/reports/unit/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini -m "not e2e" `
  --html=tests/reports/unit/report.html --self-contained-html `
  --cov --cov-config=tests/.coveragerc `
  --cov-report=html:tests/reports/unit/htmlcov --cov-report=term-missing
```

Without `--cov-report=html` only the terminal summary appears and no browsable
report is written. The raw `.coverage` database is deleted once reports are
generated.

### Behavioural tier

Results and scenario-level JSON, into `tests/reports/e2e/`. Needs the stack:

```powershell
docker compose -f compose.e2e.yaml up -d --build
$env:E2E_BASE_URL = 'http://127.0.0.1:8081'
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini -m e2e --no-cov `
  --html=tests/reports/e2e/report.html --self-contained-html `
  --cucumber-json=tests/reports/e2e/cucumber.json
.\.venv\Scripts\python.exe tests/cucumber_html.py `
  tests/reports/e2e/cucumber.json tests/reports/e2e/scenarios.html
```

`--no-cov` is deliberate: browser tests run Django in a container the in-process
coverage tool cannot observe, so including them would understate coverage rather
than add to it.

**`scenarios.html` is the readable BDD report** — features, scenarios with
pass/fail badges, and every Given/When/Then step, with error messages inline on
failure. `report.html` lists *test function* names, which for BDD are generated
and unreadable; `cucumber.json` is machine-readable but not for humans. The
renderer is a small local script (`tests/cucumber_html.py`) rather than a
dependency: the only PyPI option is an alpha release.

Add `--gherkin-terminal-reporter` for Given/When/Then output instead of dots —
useful for seeing which step failed.

**Debugging a failure.** Traces, video, and screenshots are not captured by
default — they are an on-demand debugging aid, not a deliverable. When a
scenario fails and the terminal output is not enough:

```powershell
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini -m e2e --no-cov `
  --tracing=retain-on-failure --output=tests/reports/e2e/artifacts
.\.venv\Scripts\python.exe -m playwright show-trace `
  tests/reports/e2e/artifacts/<test>/trace.zip
```

A trace is a timeline with DOM snapshots and the full network log. `--headed`
and `--slowmo=500` are often quicker for a reproducible failure.

### Scenario completeness

Not a report, but the behavioural tier's real gate — every Gherkin scenario must
be bound to a step definition:

```powershell
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini `
  --generate-missing --feature tests/features
```

It names each unbound scenario with its file and line. All 81 are currently
bound, so this reports nothing.

A quicker check that the same thing still holds — collection fails on an unbound
step, so a successful collect is the gate:

```powershell
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini tests/e2e --collect-only -q
```

Note that an editor's Gherkin plugin may flag steps in the feature files as
undefined. Most look only in step-definition modules, not in `conftest.py`,
where the shared steps live. pytest is the authority: if collection succeeds,
every step is bound.

## Current results

Measured 2026-07-29, before any gallery code exists.

| Suite | Result |
| --- | --- |
| Unit | 35 passed, 1 skipped |
| Coverage | 94% (gate: 70%) |
| Behavioural | 81 scenarios — 12 pass, 69 fail |

**The behavioural tier is meant to be red.** The scenarios were written before
the code, so they describe a gallery that has not been built. A scenario failing
with `locator resolved to 0 elements` is the specification doing its job.

Of the 12 that pass, only 6 mean anything: the four deployment smoke checks and
the two health scenarios. The other 6 are **vacuous** — assertions about
*absence* that an empty page satisfies:

| Scenario | Passes because |
| --- | --- |
| The first page has no previous page | Nothing renders, so no link exists |
| A valid page is not redirected | The placeholder returns 200 with no notice |
| An image outside the collection is not found (×4) | `/images/101` 404s because no route exists |

They become real assertions once there is a gallery to contradict them. Until
then, treat 12 as the count to watch rather than a measure of progress.

Coverage is measured on the unit tier only. Browser tests exercise Django inside
a container the in-process coverage tool cannot see, so including them would
understate coverage rather than add to it.

## What is covered

- Health endpoint status code and JSON payload
- Landing page rendering
- Settings invariants: no relational database, a cache that can be shared
  between workers, gallery defaults, and that `settings.py` is the only module
  reading `os.environ`
- The documented API contract, which fails the build when `docs/api-contract.md`
  and the routes disagree
- JSON log formatting, including quote/newline escaping and `extra=` context
- **The test suite's own integrity** — that every requirement has a scenario,
  every scenario names a real requirement and a build stage, and the cold-cache
  list has not been broken by a rename
- BDD scenarios covering health and the landing page end to end
- Browser-level verification against the running container, including that
  **every subresource the page requests returns below 400**

That last one exists because the original e2e tests asserted only on rendered
DOM content and so passed while the container served a 404 for its stylesheet —
the page looked correct to the test and broken to a user. Any test that renders
a page should assert on what the page *fetches*, not only on what it contains.

**This is the whole reason the browser tier survives server-side rendering.**
The Django test client renders templates in-process and never fetches a
subresource, so it cannot catch that class of failure at all. The application
now carries more of that surface than when the incident happened — two
stylesheets with an `@import` between them, and image bytes served through a
proxy endpoint.

## Specified but not yet implemented

`gallery.feature`, `variations.feature`, and `detail.feature` describe the Core
Requirements ahead of the code. **Their step definitions exist and run**, so all
81 scenarios are collected — and nearly all of them fail, which is the point.
The gallery has not been built yet.

| Feature file | Requirements | Scenarios |
| --- | --- | --- |
| `gallery.feature` | F1.1–F1.3, F2.1–F2.7, F5.5, resilience | 26 |
| `variations.feature` | F3.1–F3.6, custom dimensions | 32 |
| `detail.feature` | F4.1–F4.4 | 17 |
| `health.feature` | the baseline harness | 2 |

A handful pass without meaning anything: assertions about *absence* — "there is
no link to a previous page", "an image outside the collection is not found" —
are satisfied by a page that renders nothing and a route that does not exist.
They become real assertions once there is a gallery to contradict them.

### Selecting scenarios

Every scenario is tagged with the requirement it covers and the build stage it
belongs to, so slices of the suite are runnable by name:

```powershell
pytest -c tests/pytest.ini -m "F2_2"                # one requirement
pytest -c tests/pytest.ini -m "stage1"              # the first slice
pytest -c tests/pytest.ini -m "stage1 or stage2"    # cumulative
pytest -c tests/pytest.ini -m "e2e and not resilience"
```

Requirement ids use underscores (`F2_2`, not `F2.2`) because a dot is ambiguous
inside a `-m` expression. Tags are declared in `pytest.ini`; `--strict-markers`
turns a typo into a failed run rather than a scenario nobody can select.

`tests/unit/test_requirement_coverage.py` keeps the tags honest: it fails if a
documented requirement has no scenario, if a scenario names a requirement that
does not exist, if a tag is undeclared, or if a scenario carries no build stage.

### Build order

The stages encode dependency — a scenario in stage N relies only on stages
before it — so they are a sequence, not a grouping.

| Stage | Covers | Why here |
| --- | --- | --- |
| 1 | Metadata endpoint and the grid | Nothing else can be asserted until tiles render |
| 2 | The image proxy, one call per tile | Real bytes, and the cache path |
| 3 | Pagination | Needs a grid to page through |
| 4 | The image-count control | Needs the grid; F2.5 requires a real control |
| 5 | Notices and invalid-page recovery | Unblocks every validation scenario in `variations` |
| 6 | Resilience | The subtlest logic; wants a working proxy first |
| 7 | Size and filter parameters | Renders into the grid from stage 1 |
| 8 | Variation validation and persistence | Needs both notices (5) and variations (7) |
| 9 | The detail view | Opened from the grid |
| 10 | Filters and the parameters panel on detail | Needs variations carrying over |

`gallery.feature` comes first because it is the only feature depending on no
other. `detail.feature` comes last: eight of its scenarios assert that filters
carry over from the gallery, so they cannot pass before `variations` does.

See [docs/core-features.md](../docs/core-features.md) for the requirement IDs
and the decisions those scenarios encode.

## Out of scope

**F5.1–F5.4 have no Gherkin and never will.** "All logic on the backend",
"templates must not construct URLs", "centralise in a service layer", and "use
URL reversing" are code-structure properties, unobservable from outside the
application — a hardcoded correct URL is indistinguishable from a reversed one
when viewed through a client. They belong to unit tests that inspect structure
directly. F5.5 is the exception: caching is observable, because a repeated
request must not produce a second upstream call, so it has a scenario.

That exemption is recorded in `UNCOVERED_BY_DESIGN` in
`tests/unit/test_requirement_coverage.py`, and a test fails if one of those four
ever acquires a scenario — an exemption that stops being true should be removed,
not left implying the requirement is untestable.

Also out of scope until the features land: upstream picsum.dev integration and
concurrency validation. The resilience matrix does have Gherkin — six scenarios
tagged `@resilience`, covering per-tile failure, stale-cache fallback, and
timeout behaviour per [ADR 12](../docs/adr/0012-resilience-strategy.md).

## Adding a BDD scenario

1. Add or extend a `.feature` file in `features/`.
2. Tag it with the requirement it covers and the build stage it belongs to —
   `@F3_4 @stage7`. Declare any new tag in `pytest.ini`, or `--strict-markers`
   fails the run.
3. Add matching step definitions in `e2e/`, in a file named `test_*.py`. If the
   step is used by more than one feature file, put it in `e2e/conftest.py`
   instead, where pytest-bdd resolves it for all of them.
4. Bind the file with `scenarios("<name>.feature")` — paths resolve relative to
   `features/` via `bdd_features_base_dir`.

Steps stay **business-facing and declarative**: "the gallery is available", not
"the fake upstream returns 200". The fault-injection mechanism is a
step-definition detail and must not appear in the Gherkin.

**Assert through the browser.** A step drives the page and reads the DOM; it
does not import Django, build a view, or use the test client. Find elements by
`data-testid`, never by CSS class, so restyling cannot break a test.

The one exception is the fake upstream's request log. Scenarios asserting on
upstream call counts (`Then 10 upstream image requests are made`) read it,
because the browser cannot see what Django fetched. Those steps must genuinely
count — asserting on rendered tiles instead would let an uncached implementation
pass.

**Behaviour belongs in a scenario, not in a unit test.** The gallery is
client-rendered, so the Django test client cannot verify it — it does not run
JavaScript and would only ever see an empty shell. Reserve `unit/` for
configuration, contracts, and pure logic. See
[ADR 15](../docs/adr/0015-test-strategy.md).
