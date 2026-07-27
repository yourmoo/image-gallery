# Tests

All test code and test configuration live in this directory.

```text
tests/
  README.md             this guide — the single source for testing docs
  pytest.ini            pytest configuration (rootdir when passed via -c)
  .coveragerc           coverage configuration
  conftest.py           shared fixtures
  unit/                 fast tests via the Django test client
  features/             Gherkin .feature files
  bdd/                  pytest-bdd step definitions for those features
  e2e/                  Playwright browser tests (marked `e2e`)
  reports/              generated coverage output (gitignored)
```

Because the configuration is not at the project root, **every command must pass
`-c tests/pytest.ini`**. Run them from the project root.

A bare `pytest` with no `-c` still collects and runs, but silently without the
markers, BDD feature path, and Django settings — so always include the flag.

## Strategy

Unit and BDD tests use the Django test client and run in-process, so the fast
loop needs no server, no container, and no network. They carry the coverage
gate.

Playwright tests need a real server and a real browser, which makes them slower
and dependent on something already running. They are marked `e2e` and
deselected by default so that the common case stays fast; CI and pre-submission
checks run them explicitly.

BDD sits on top of the same in-process client rather than the browser. The
Gherkin layer is there to express behaviour in the brief's own language, not to
add a second slow tier.

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

## End-to-end tests

The Playwright tests drive a real browser against a **running server**, so start
one first. Using the container:

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

## Current results

| Suite | Result |
| --- | --- |
| Unit + BDD | 13 passed |
| Coverage | 93% (gate: 70%) |
| Playwright e2e | 4 passed |
| Total | 17 passed |

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

## Out of scope

Everything gallery-specific — upstream picsum.dev integration, transformations,
parameter validation, pagination, caching behaviour, and the error-handling
matrix — because those features are not implemented yet. Tests arrive with the
features.

## Adding a BDD scenario

1. Add or extend a `.feature` file in `features/`.
2. Add matching step definitions in `bdd/`, in a file named `test_*.py`.
3. Bind them with `scenarios("<name>.feature")` — paths resolve relative to
   `features/` via `bdd_features_base_dir`.
