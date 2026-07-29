"""Render a Cucumber JSON report as a single self-contained HTML page.

pytest-bdd emits Cucumber JSON, and pytest-html reports *test function* names
rather than scenario names — neither gives a readable Given/When/Then summary.
This turns the JSON into one, with no extra dependency: the only alternative on
PyPI is an alpha release, which is not worth adding to a graded submission.

Lives at `tests/` rather than `tests/e2e/` even though the e2e tier is its only
consumer: it is suite tooling, like `conftest.py` beside it, not a test. Keeping
it out of `e2e/` means that directory holds step definitions and browser tests
only. (Collection is unaffected either way — pytest only collects `test_*.py`.)

Usage:

    pytest -c tests/pytest.ini -m e2e --cucumber-json=tests/reports/e2e/cucumber.json
    python tests/cucumber_html.py tests/reports/e2e/cucumber.json \\
        tests/reports/e2e/scenarios.html
"""

from __future__ import annotations

import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Keep the styling in step with docs/ui/design-system.md: same neutral palette,
# same restraint. It is a report, not a dashboard.
_CSS = """
*,*::before,*::after{box-sizing:border-box}
body{margin:0;padding:2rem 1rem 4rem;background:#FDFDFC;color:#1B1B19;
 font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:60rem;margin:0 auto}
h1{font-size:1.75rem;margin:0 0 .25rem;letter-spacing:-.02em}
.sub{color:#6E6E68;font-size:.875rem;margin:0 0 2rem}
.totals{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:2rem}
.chip{border:1px solid #E2E2DD;border-radius:999px;padding:.25rem .75rem;
 font-size:.8125rem;background:#fff}
.chip b{font-variant-numeric:tabular-nums}
.chip--passed{border-color:#BFD8BF;background:#F4F9F4}
.chip--failed{border-color:#E0BDBD;background:#FBF4F4}
.chip--skipped{border-color:#E3D08A;background:#FDF9EE}
.feature{border:1px solid #E2E2DD;border-radius:8px;margin-bottom:1.5rem;
 background:#fff;overflow:hidden}
.feature>h2{font-size:1rem;margin:0;padding:.75rem 1rem;background:#F2F2EF;
 border-bottom:1px solid #E2E2DD}
.scenario{border-top:1px solid #F2F2EF;padding:.75rem 1rem}
.scenario:first-of-type{border-top:0}
.scenario>h3{font-size:.9375rem;font-weight:600;margin:0 0 .5rem;
 display:flex;gap:.5rem;align-items:baseline;flex-wrap:wrap}
.tags{display:flex;gap:.25rem;flex-wrap:wrap;margin-left:auto}
.tag{font-size:.6875rem;font-weight:600;letter-spacing:.02em;
 padding:.125rem .4375rem;border-radius:4px;border:1px solid #E2E2DD;
 color:#6E6E68;background:#F7F7F5;font-variant-numeric:tabular-nums}
.tag--req{border-color:#DFE6F0;background:#F5F8FC;color:#2C5385}
.summary{border:1px solid #E2E2DD;border-radius:8px;background:#fff;
 margin-bottom:1.5rem;overflow:hidden}
.summary>h2{font-size:1rem;margin:0;padding:.75rem 1rem;background:#F2F2EF;
 border-bottom:1px solid #E2E2DD}
.summary table{width:100%;border-collapse:collapse;font-size:.875rem}
.summary th{text-align:left;font-weight:600;color:#6E6E68;font-size:.8125rem;
 padding:.5rem 1rem;border-bottom:1px solid #F2F2EF}
.summary td{padding:.4375rem 1rem;border-bottom:1px solid #F2F2EF}
.summary tr:last-child td{border-bottom:0}
.bar{display:inline-flex;height:.5rem;width:8rem;border-radius:999px;
 overflow:hidden;background:#F2F2EF;vertical-align:middle;margin-right:.5rem}
.bar i{display:block;height:100%}
.bar .ok{background:#8FBF92}
.bar .no{background:#D89A9A}
.count{font-variant-numeric:tabular-nums;color:#6E6E68;font-size:.8125rem}
.badge{font-size:.6875rem;text-transform:uppercase;letter-spacing:.08em;
 padding:.125rem .5rem;border-radius:999px;font-weight:600}
.badge--passed{background:#E8F3E8;color:#2F6B33}
.badge--failed{background:#F7E7E7;color:#8C2F2F}
.badge--skipped{background:#FBF2DA;color:#6B5310}
.steps{margin:0;padding:0;list-style:none;font-size:.875rem}
.steps li{padding:.1875rem 0;color:#3A3A36;display:flex;gap:.5rem}
.kw{color:#6E6E68;min-width:4.5rem;font-weight:600}
.err{white-space:pre-wrap;font:13px ui-monospace,SFMono-Regular,Menlo,monospace;
 background:#FBF4F4;border:1px solid #E0BDBD;border-radius:6px;
 padding:.625rem .75rem;margin-top:.5rem;overflow-x:auto}
footer{color:#6E6E68;font-size:.8125rem;margin-top:2rem}
"""


def _status(steps: list[dict]) -> str:
    """A scenario is as bad as its worst step."""
    seen = {step.get("result", {}).get("status", "skipped") for step in steps}

    for status in ("failed", "undefined", "pending", "skipped"):
        if status in seen:
            return "failed" if status in {"failed", "undefined"} else "skipped"

    return "passed"


def _tags(element: dict) -> list[str]:
    """Tag names on a scenario, in the order they were written.

    pytest-bdd emits Gherkin tags as ``[{"name": "F2_7", "line": 38}, ...]``.
    """
    return [t["name"] for t in element.get("tags", []) if t.get("name")]


def _is_requirement(tag: str) -> bool:
    """A requirement id from docs/core-features.md, as tagged: F2_7."""
    return bool(re.fullmatch(r"F\d+_\d+", tag))


def _requirement_summary(rows: list[tuple[str, str]]) -> str:
    """Pass/fail per requirement, so coverage is legible without reading each
    scenario.

    Only requirement tags appear: stage tags describe build order, which is a
    property of the plan rather than of the run.
    """
    by_requirement: dict[str, Counter[str]] = {}
    for tag, status in rows:
        by_requirement.setdefault(tag, Counter())[status] += 1

    if not by_requirement:
        return ""

    lines = []
    for tag in sorted(by_requirement, key=lambda t: [int(n) for n in t[1:].split("_")]):
        counts = by_requirement[tag]
        passed, total = counts["passed"], sum(counts.values())
        pct = (passed / total * 100) if total else 0
        failed_pct = 100 - pct
        lines.append(
            f"<tr><td><span class='tag tag--req'>{html.escape(tag)}</span></td>"
            f"<td><span class='bar'>"
            f"<i class='ok' style='width:{pct:.0f}%'></i>"
            f"<i class='no' style='width:{failed_pct:.0f}%'></i></span>"
            f"<span class='count'>{passed}/{total}</span></td></tr>"
        )

    return (
        "<section class='summary'><h2>Requirement coverage</h2>"
        "<table><thead><tr><th>Requirement</th><th>Scenarios passing</th></tr>"
        f"</thead><tbody>{''.join(lines)}</tbody></table></section>"
    )


def render(report: list[dict]) -> str:
    counts: Counter[str] = Counter()
    body: list[str] = []
    requirement_rows: list[tuple[str, str]] = []

    for feature in report:
        scenarios: list[str] = []

        for element in feature.get("elements", []):
            steps = element.get("steps", [])
            status = _status(steps)
            counts[status] += 1

            tags = _tags(element)
            for tag in tags:
                if _is_requirement(tag):
                    requirement_rows.append((tag, status))

            tag_html = "".join(
                f'<span class="tag{" tag--req" if _is_requirement(t) else ""}">'
                f"{html.escape(t)}</span>"
                for t in tags
            )
            tag_block = f'<span class="tags">{tag_html}</span>' if tag_html else ""

            rows = "".join(
                f'<li><span class="kw">{html.escape(s.get("keyword", "").strip())}</span>'
                f'<span>{html.escape(s.get("name", ""))}</span></li>'
                for s in steps
            )

            errors = "".join(
                f'<div class="err">{html.escape(s["result"]["error_message"])}</div>'
                for s in steps
                if s.get("result", {}).get("error_message")
            )

            scenarios.append(
                f'<div class="scenario"><h3>'
                f'<span class="badge badge--{status}">{status}</span>'
                f'{html.escape(element.get("name", "(unnamed)"))}'
                f"{tag_block}</h3>"
                f'<ul class="steps">{rows}</ul>{errors}</div>'
            )

        if scenarios:
            body.append(
                f'<section class="feature"><h2>'
                f'{html.escape(feature.get("name", "(unnamed feature)"))}</h2>'
                f'{"".join(scenarios)}</section>'
            )

    total = sum(counts.values())
    chips = "".join(
        f'<span class="chip chip--{name}">{name} <b>{counts[name]}</b></span>'
        for name in ("passed", "failed", "skipped")
        if counts[name]
    )

    if not body:
        body.append(
            '<section class="feature"><h2>No scenarios</h2><div class="scenario">'
            "<p>The report contained no scenarios. Feature files with no step "
            "definitions are not collected and so do not appear here — run with "
            "<code>--generate-missing</code> to list them.</p></div></section>"
        )

    return (
        f"<!doctype html><html lang=en><head><meta charset=utf-8>"
        f"<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Scenario report</title><style>{_CSS}</style></head><body><main>"
        f"<h1>Scenario report</h1>"
        f'<p class="sub">{total} scenario{"s" if total != 1 else ""} '
        f'across {len(report)} feature{"s" if len(report) != 1 else ""}</p>'
        f'<div class="totals">{chips}</div>'
        f'{_requirement_summary(requirement_rows)}{"".join(body)}'
        f"<footer>Generated from Cucumber JSON emitted by pytest-bdd.</footer>"
        f"</main></body></html>"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2

    source, destination = Path(argv[1]), Path(argv[2])

    if not source.exists():
        print(f"No Cucumber JSON at {source}. Run the e2e suite first.")
        return 1

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render(json.loads(source.read_text(encoding="utf-8"))), encoding="utf-8"
    )
    print(f"Scenario report written to {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
