# 15. Test strategy: Playwright for behaviour, units for coverage

## Context

[ADR 2](0002-client-side-rendering.md) makes the browser build the DOM. The
Django test client cannot execute JavaScript, so it would only ever see an empty
application shell — it can no longer verify any gallery behaviour, and the
in-process BDD tier that server-side rendering had restored is gone again.

That leaves two questions the brief asks directly:

- **Line 173** requires at least 70% automated test coverage. Browser tests
  exercise Django inside a container, which the in-process coverage tool cannot
  observe, so they contribute nothing to that number.
- **Lines 171–172** require unit tests for service, transformations, and
  validation, plus integration tests at the API boundary.

And one the project has set for itself: 74 Gherkin scenarios exist as the
behavioural specification, and they must actually be implemented rather than
quietly left unbound.

## Decision

Two tiers, with **different measures of completeness**.

| Tier | Verifies | Measured by |
| --- | --- | --- |
| `unit/` | Modules in isolation, and the JSON API boundary | **Coverage ≥70%** |
| `e2e/` | All 74 Gherkin scenarios, in a real browser | **Every scenario bound** |

The Django test client is retained **only** for JSON API tests, where no
JavaScript is involved and a request/response assertion is exactly the right
tool. It is not used for gallery behaviour.

**Every Gherkin scenario runs in the browser tier, without exception.**
`health.feature` could run in-process — a JSON endpoint and a static shell
involve no JavaScript — but splitting Gherkin across two tiers would mean two
scenario reports and two places to look for "did the specification pass?". Two
extra browser tests is a negligible cost against one uniform answer.

### Coverage is a unit-test measure

`tests/unit/` carries the 70% gate alone. This is deliberate rather than a
concession: the modules that most need coverage — `validation.py`,
`provider.py`, `cache.py`, `gallery.py` — are pure or near-pure and fully
exercisable in-process. Testing the URL translation, the allow-lists, the
dimension grammar, the cache tiering, and the fallback logic directly is more
precise than inferring them through a browser.

The JSON API is tested in this tier too, through the Django test client:
parameter validation, error payloads, and status codes are request/response
assertions that need no browser.

### Gherkin completeness is the behavioural measure

Coverage percentage does not describe behavioural completeness here. The
equivalent measure is that **every scenario in `tests/features/` is bound to a
step definition**, enforced mechanically:

    pytest -c tests/pytest.ini --generate-missing --feature tests/features

This reports, by file and line, any scenario with no implementation. It is a CI
gate: an unimplemented scenario fails the build. A specification that silently
goes unimplemented is the failure mode this prevents, and it is a stronger
guarantee than a coverage percentage — 100% line coverage says nothing about
whether pagination was ever exercised.

### Reporting

**The tiers report separately**, into `tests/reports/unit/` and
`tests/reports/e2e/`. They measure different things, so a merged report would
blur both: one would show a coverage percentage against scenarios it did not
measure, and a scenario list against modules it did not exercise.

    tests/reports/
      unit/  report.html, htmlcov/index.html
      e2e/   report.html, scenarios.html, cucumber.json

| Tier | Artifact | Produced by |
| --- | --- | --- |
| unit | Test report | `--html=tests/reports/unit/report.html --self-contained-html` |
| unit | Coverage | `--cov --cov-report=html:tests/reports/unit/htmlcov` |
| e2e | Test report | `--html=tests/reports/e2e/report.html --self-contained-html` |
| e2e | Scenario results | `--cucumber-json=tests/reports/e2e/cucumber.json` |
| e2e | **Readable scenario report** | `tests/cucumber_html.py` renders the JSON to `scenarios.html` |
| e2e | Readable Gherkin, terminal | `--gherkin-terminal-reporter` |

**The scenario report is the behavioural tier's headline artifact**, because
this tier's measure is scenarios passing rather than a percentage. Neither
available format serves that directly: `pytest-html` lists *test function*
names, which pytest-bdd generates and which do not read as behaviour, and
Cucumber JSON is machine-readable only. A small local script renders the JSON
into features, scenarios with pass/fail badges, and full Given/When/Then steps
with inline errors. It is a script rather than a dependency because the only
PyPI alternative is an alpha release, which is not worth adding to a graded
submission.

The behavioural tier runs with `--no-cov`: browser tests exercise Django in a
container the in-process coverage tool cannot observe, so including them would
*understate* coverage rather than add to it.

**Trace, video, and screenshot capture are deliberately not part of the standard
run.** Playwright can record all three, and a trace — a timeline with DOM
snapshots and the full network log — is the fastest way to diagnose a failing
browser test. But they are a debugging aid rather than a deliverable: they slow
the run, produce artifacts nobody reads when tests pass, and none of them is
required by the brief. They are documented in `tests/README.md` as an on-demand
flag for when a failure needs investigating.

## Consequences

**Behavioural tests need a running container.** The fast inner loop is unit
tests only; verifying a scenario means starting the application. This is the
principal cost of [ADR 2](0002-client-side-rendering.md) and it is real —
feedback on gallery behaviour is seconds rather than milliseconds.

**Browser tests are slower and can flake.** Mitigations: assert on
`data-testid` attributes rather than styling or text where possible, wait on
application state rather than timeouts, and never assert on elapsed time. The
concurrency test asserts call counts, never milliseconds
([ADR 14](0014-concurrency-validation.md)).

**Upstream must be stubbed at the container boundary.** Scenarios such as "the
gallery is unavailable for 3 of the images" need deterministic upstream failure,
and the browser tier cannot patch a Python object in another process. The
provider therefore needs a test mode configurable by environment variable, so
the container can be started with a scripted upstream. This is new machinery
that in-process testing did not require.

**The 70% gate reflects the service layer, not the gallery.** An interviewer
asking "what does your coverage number mean?" should be told plainly: it
measures unit-level exercise of validation, translation, caching, and
composition. Behavioural completeness is measured by Gherkin binding, not by
this number.

**Two reports tell the whole story**, and both belong in the README: the
coverage percentage for the service layer, and the Cucumber JSON showing every
scenario passing.

## Alternatives rejected

**Keep the Django test client for behaviour.** Impossible under
[ADR 2](0002-client-side-rendering.md) — it cannot execute JavaScript and would
assert against an empty shell.

**Count browser tests toward coverage** by running `coverage` inside the
container and combining data files. Technically possible with
`COVERAGE_PROCESS_START` and `coverage combine`. Rejected as machinery that
complicates the container for a number that would be reported more honestly by
keeping the tiers separate.

**Drop Gherkin and write Playwright tests directly.** Fewer moving parts.
Rejected because the feature files are the behavioural specification, written in
the brief's own language and traceable to requirement IDs — that traceability is
what makes completeness checkable.

**Skip the browser tier and test only the JSON API.** Fast, and it would cover
the backend thoroughly. Rejected because it verifies nothing the user sees: the
grid, pagination controls, notices, and parameters panel are all rendered
client-side, so an API-only suite would leave the entire user-facing surface
unverified.
