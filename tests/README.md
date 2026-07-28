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
  e2e/                  step definitions, Playwright (marked `e2e`)
  reports/              generated coverage and report output (gitignored)
```

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
carries the 70% gate alone. That is the right place for it: `validation.py`,
`provider.py`, `cache.py`, and `gallery.py` are pure or near-pure and are more
precisely tested directly than inferred through a browser. The JSON API is
tested here too, through the Django test client — request/response assertions
need no browser.

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

The Playwright tests drive a real browser against a **running server**, so start
one first. This is where every Gherkin scenario runs.

Alongside the scenarios, this tier keeps a few deployment checks that only a
real browser can make:

- Every subresource the page requests returns below 400
- Declared assets resolve and have the right content type
- An `<img>` served by the proxy endpoint actually renders

Using the container:

```powershell
docker compose up -d
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini -m e2e --no-cov
docker compose down
```

The default target is `http://localhost:8080`, which matches the port published
by `compose.yaml`. Point the suite elsewhere with `E2E_BASE_URL`:

```powershell
$env:E2E_BASE_URL = 'http://localhost:8000'
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini -m e2e --no-cov
```

That form is useful against a local `image-gallery-admin runserver` instead of
the container.

Useful Playwright flags: `--headed` to watch the browser, `--slowmo=500` to slow
it down, `--browser firefox` to switch engine (install it first with
`playwright install firefox`).

## Everything at once

Requires a running server, since the e2e tests are included:

```powershell
docker compose up -d
.\.venv\Scripts\python.exe -m pytest -c tests/pytest.ini
```

## Reports

All artifacts land in `tests/reports/`, which is gitignored.

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

Results and scenario-level JSON, into `tests/reports/e2e/`. Needs a running
server:

```powershell
docker compose up -d
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

It names each unbound scenario with its file and line.

## Current results

| Suite | Result |
| --- | --- |
| Unit | 17 passed |
| Coverage | 93% (gate: 70%) |
| Browser (2 BDD scenarios + 4 smoke) | 6 passed |
| Total | 23 passed |

Coverage is measured on the in-process tiers only. Browser tests exercise Django
inside a container the coverage tool cannot see, so `unit/` and `bdd/` carry the
70% gate between them.

## What is covered

- Health endpoint status code and JSON payload
- Landing page rendering
- Settings invariants: no relational database, bounded cache, gallery defaults,
  and that `settings.py` is the only module reading `os.environ`
- JSON log formatting, including quote/newline escaping and `extra=` context
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
Requirements ahead of the code, following the brief's own language. They have
**no step definitions yet**, so pytest-bdd does not collect them and they do not
affect the counts above. Each becomes live when its steps are written alongside
the feature it specifies.

| Feature file | Requirements | Cases |
| --- | --- | --- |
| `gallery.feature` | F1.1–F1.3, F2.1–F2.7, F5.5, resilience | 23 |
| `variations.feature` | F3.1–F3.6, custom dimensions | 32 |
| `detail.feature` | F4.1–F4.4 | 17 |

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

Also out of scope until the features land: upstream picsum.dev integration, the
resilience matrix (timeout, retry, fallback), and concurrency validation.

## Adding a BDD scenario

1. Add or extend a `.feature` file in `features/`.
2. Add matching step definitions in `bdd/`, in a file named `test_*.py`.
3. Bind them with `scenarios("<name>.feature")` — paths resolve relative to
   `features/` via `bdd_features_base_dir`.

Steps stay **business-facing and declarative**: "the gallery is available", not
"the provider stub returns 200". The mocking mechanism is a step-definition
detail and must not appear in the Gherkin.

Upstream is stubbed at the provider boundary, so scenarios asserting on upstream
call counts (`Then 10 upstream image requests are made`) count calls to that
stub. Those steps must genuinely count — asserting on rendered tiles instead
would let a serial or uncached implementation pass.

**Do not add browser tests for behaviour.** If a scenario can be verified
through the test client, it belongs here. The browser tier is for deployment
correctness only — see [Strategy](#strategy).
