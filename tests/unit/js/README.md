# Client unit tests

The other half of the unit tier. `unit/python/` covers the Django modules,
`features/` covers behaviour through a browser, and this covers the **client's
own logic** — the arithmetic and mapping that run in the browser and are not
reachable from Python.

It exists because [ADR 20](../../../docs/adr/0020-ids-are-derived-in-the-browser.md)
put page arithmetic on both sides of the wire. `image_gallery/gallery.py` and
`static/js/derive.js` compute the same id range, and a divergence between them
would show as tiles requesting ids the server considers out of range. Testing
only the Python half would leave the half that decides what a user actually
sees covered by nothing but end-to-end scenarios.

## Running them

Node is **not installed locally** and does not need to be. The tests run in a
throwaway container, which is also how CI runs them:

```powershell
docker run --rm -v "${PWD}:/app" -w /app node:22-slim `
  node --test --test-reporter=spec "tests/unit/js/*.test.js"
```

There is no `package.json`, no `node_modules`, and no build step. The runner is
Node's own (`node:test`), the assertions are `node:assert/strict`, and the
modules under test are plain ESM that the browser loads directly — the same
files ship, untransformed.

`tests/js_tests.py` wraps the command above and additionally writes the HTML
report:

```powershell
python tests/js_tests.py            # run + write tests/reports/unit/js/report.html
python tests/js_tests.py --no-report
```

## What belongs here

Only **pure** functions — no DOM, no `fetch`, no `window`. That constraint is
the reason `static/js/` is split in two:

| Module | Contents | Tested here |
| --- | --- | --- |
| `derive.js` | Id arithmetic, notice text, bounds parsing | **Yes** |
| `gallery.js` | DOM construction, event wiring, `location` | No — browser tier |

Keeping the pure half separate is what lets it be tested without jsdom or a
headless browser, and it is a real design constraint rather than a testing
convenience: logic that needs a DOM to run is logic that cannot be checked
cheaply.

Anything requiring a document belongs in `features/`, where a real browser
renders it.

## Reports

`tests/reports/unit/js/report.html`, alongside `reports/unit/python/` and `reports/e2e/`.
Generated from the runner's JUnit XML, so it reflects exactly what ran.
