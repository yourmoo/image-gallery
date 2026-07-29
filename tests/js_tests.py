"""Run the client unit tests and render their report.

The JS tier has no local toolchain: Node runs in a throwaway container, which
is also how CI runs it, so nothing needs installing to work on this project.
This script wraps that invocation and turns the runner's JUnit XML into an HTML
report beside the other two tiers'.

Lives at `tests/` rather than in a `tools/` directory, matching
`cucumber_html.py`: it is suite tooling, not a test. pytest collects `test_*.py`
only, so the name keeps it out of collection.

Usage:

    python tests/js_tests.py                 run, write tests/reports/unit/js/report.html
    python tests/js_tests.py --no-report     run only
    python tests/js_tests.py --node          use a local node instead of Docker

Exits non-zero if any test fails, so it can gate a build.
"""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "tests" / "reports" / "unit" / "js"
REPORT_PATH = REPORT_DIR / "report.html"
LCOV_PATH = REPORT_DIR / "lcov.info"

# Pinned rather than `node:latest` so a Node release cannot change what the
# suite runs without the change being visible in a diff.
NODE_IMAGE = "node:22-slim"

# A directory argument resolves as a CommonJS module path and fails; the glob is
# what Node's test runner expects here.
TEST_GLOB = "tests/unit/js/*.test.js"

# The Python tier gates at 70% (tests/.coveragerc). This tier is held higher
# because it covers pure functions with no I/O, no framework, and no branches
# that are awkward to reach -- anything uncovered here is simply untested.
COVERAGE_FLOOR = 90.0


@dataclass
class Case:
    suite: str
    name: str
    time: float
    failure: str | None = None

    @property
    def passed(self) -> bool:
        return self.failure is None


@dataclass
class FileCoverage:
    """Line and branch coverage for one source file, read from LCOV."""

    path: str
    lines_hit: int
    lines_found: int
    branches_hit: int
    branches_found: int
    uncovered: list[int]

    @property
    def line_percent(self) -> float:
        return 100.0 * self.lines_hit / self.lines_found if self.lines_found else 100.0

    @property
    def branch_percent(self) -> float:
        return (
            100.0 * self.branches_hit / self.branches_found
            if self.branches_found
            else 100.0
        )


def run_tests(use_local_node: bool) -> tuple[str, int]:
    """Run the suite and return its JUnit XML and exit code.

    Coverage is collected in the same run and written to `lcov.info` — two
    reporters cannot both target stdout, so the JUnit report comes back here
    and the LCOV goes to a file the parser reads afterwards.

    `--test-coverage-exclude` keeps the test files themselves out of the
    figures; a suite that counts its own lines reports a number that rises
    whenever anyone writes more tests.
    """
    if use_local_node:
        if not shutil.which("node"):
            sys.exit("node is not on PATH; omit --node to run it in Docker")
        command = ["node"]
    else:
        if not shutil.which("docker"):
            sys.exit("docker is not available, and --node was not given")
        command = [
            "docker", "run", "--rm",
            "-v", f"{REPO_ROOT}:/app",
            "-w", "/app",
            NODE_IMAGE,
            "node",
        ]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    lcov_target = LCOV_PATH.relative_to(REPO_ROOT).as_posix()

    command += [
        "--test",
        "--experimental-test-coverage",
        "--test-coverage-exclude=tests/**",
        "--test-reporter=junit",
        "--test-reporter-destination=stdout",
        "--test-reporter=lcov",
        f"--test-reporter-destination={lcov_target}",
        TEST_GLOB,
    ]

    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
    return result.stdout, result.returncode


def parse_coverage() -> list[FileCoverage]:
    """Read the LCOV the runner wrote.

    LCOV is line-oriented and small: DA records are per-line hit counts, BRDA
    per-branch. Parsing it directly avoids a dependency for what amounts to a
    dozen lines of accumulation.
    """
    if not LCOV_PATH.exists():
        return []

    files: list[FileCoverage] = []
    path = ""
    hits: dict[int, int] = {}
    branches: list[int] = []

    for line in LCOV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("SF:"):
            path, hits, branches = line[3:].strip(), {}, []
        elif line.startswith("DA:"):
            number, count = line[3:].split(",")[:2]
            hits[int(number)] = int(count)
        elif line.startswith("BRDA:"):
            taken = line[5:].split(",")[3]
            branches.append(0 if taken == "-" else int(taken))
        elif line.startswith("end_of_record") and path:
            files.append(
                FileCoverage(
                    path=path,
                    lines_hit=sum(1 for count in hits.values() if count > 0),
                    lines_found=len(hits),
                    branches_hit=sum(1 for count in branches if count > 0),
                    branches_found=len(branches),
                    uncovered=sorted(n for n, count in hits.items() if count == 0),
                )
            )
            path = ""

    return files


def parse(xml_text: str) -> list[Case]:
    """Read the runner's JUnit XML into a flat list of cases.

    The runner emits one `<testsuite>` per `describe` block. Anything before
    the XML declaration is Docker noise (an image pull, say) and is discarded.
    """
    start = xml_text.find("<?xml")
    if start == -1:
        return []

    try:
        root = ET.fromstring(xml_text[start:])
    except ET.ParseError:
        return []

    def read(case, suite_name: str) -> Case:
        failure = case.find("failure")
        error = case.find("error")
        detail = failure if failure is not None else error
        return Case(
            suite=suite_name,
            name=case.get("name", "—"),
            time=float(case.get("time", 0) or 0),
            failure=(detail.get("message") or detail.text or "failed").strip()
            if detail is not None
            else None,
        )

    cases = []
    for suite in root.iter("testsuite"):
        cases.extend(read(case, suite.get("name", "—")) for case in suite.findall("testcase"))

    # A file that fails to load produces a `<testcase>` directly under
    # `<testsuites>`, with no suite around it — an import error, most often.
    # Without this the run reports "no results parsed" and hides the reason.
    cases.extend(read(case, "load errors") for case in root.findall("testcase"))

    return cases


# Styling deliberately matches tests/cucumber_html.py: same neutral palette,
# same restraint. It is a report, not a dashboard.
STYLE = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  color: #1a1a1a; background: #fff;
  margin: 0 auto; padding: 2rem 1rem; max-width: 60rem;
}
h1 { font-size: 1.25rem; margin: 0 0 .25rem; }
.sub { color: #5a5a5a; font-size: .8125rem; margin: 0 0 1.5rem; }
.summary { display: flex; gap: 1.5rem; padding: .75rem 1rem; margin-bottom: 1.5rem;
  border: 1px solid #d8d8d8; border-radius: 6px; background: #f7f8f9; }
.summary div { font-size: .8125rem; color: #5a5a5a; }
.summary strong { display: block; font-size: 1.25rem; color: #1a1a1a; }
.pass strong { color: #1e6b3a; }
.fail strong { color: #a3271f; }
h2 { font-size: .9375rem; margin: 1.5rem 0 .5rem; }
table { width: 100%; border-collapse: collapse; }
td { padding: .375rem .5rem; border-bottom: 1px solid #eee; vertical-align: top; }
td.mark { width: 1.5rem; }
td.time { width: 5rem; text-align: right; color: #5a5a5a;
  font: .75rem ui-monospace, monospace; }
td.pct { width: 6rem; text-align: right;
  font: .8125rem ui-monospace, monospace; }
.ok { color: #1e6b3a; }
.no { color: #a3271f; }
pre { margin: .25rem 0 .5rem; padding: .5rem .75rem; overflow-x: auto;
  background: #fdf2f1; border-left: 2px solid #a3271f;
  font: .75rem ui-monospace, monospace; }
footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #d8d8d8;
  color: #5a5a5a; font-size: .8125rem; }
code { background: #f7f8f9; padding: .1rem .3rem; border-radius: 3px;
  font: .8125rem ui-monospace, monospace; }
"""


def render(cases: list[Case], coverage: list[FileCoverage]) -> str:
    passed = sum(case.passed for case in cases)
    failed = len(cases) - passed
    total_time = sum(case.time for case in cases)

    lines_found = sum(f.lines_found for f in coverage)
    lines_hit = sum(f.lines_hit for f in coverage)
    overall = 100.0 * lines_hit / lines_found if lines_found else 100.0

    coverage_rows = "".join(
        f"<tr><td>{html.escape(f.path)}</td>"
        f'<td class="pct">{f.line_percent:.1f}%</td>'
        f'<td class="pct">{f.branch_percent:.1f}%</td>'
        f'<td class="time">{", ".join(str(n) for n in f.uncovered) or "—"}</td></tr>'
        for f in coverage
    )
    coverage_section = (
        "<h2>Coverage</h2><table>"
        '<tr><td><strong>File</strong></td><td class="pct"><strong>Lines</strong></td>'
        '<td class="pct"><strong>Branches</strong></td>'
        '<td class="time"><strong>Uncovered</strong></td></tr>'
        f"{coverage_rows}</table>"
        if coverage
        else ""
    )

    rows = []
    for suite in dict.fromkeys(case.suite for case in cases):
        rows.append(f"<h2>{html.escape(suite)}</h2><table>")
        for case in (c for c in cases if c.suite == suite):
            mark = '<span class="ok">✔</span>' if case.passed else '<span class="no">✘</span>'
            rows.append(
                f'<tr><td class="mark">{mark}</td>'
                f"<td>{html.escape(case.name)}"
                + (f"<pre>{html.escape(case.failure)}</pre>" if case.failure else "")
                + f'</td><td class="time">{case.time * 1000:.1f} ms</td></tr>'
            )
        rows.append("</table>")

    status_class = "fail" if failed else "pass"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Client unit tests</title><style>{STYLE}</style></head><body>
<h1>Client unit tests</h1>
<p class="sub">The browser's own logic — id derivation, bounds parsing, and
notice text — tested without a DOM. See <code>tests/unit/js/README.md</code>.</p>
<div class="summary">
  <div class="{status_class}"><strong>{passed}/{len(cases)}</strong>passing</div>
  <div class="{"pass" if overall >= COVERAGE_FLOOR else "fail"}">
    <strong>{overall:.0f}%</strong>lines covered</div>
  <div><strong>{len(set(c.suite for c in cases))}</strong>modules</div>
  <div><strong>{total_time * 1000:.0f} ms</strong>total</div>
</div>
{"".join(rows)}
{coverage_section}
<footer>
  <code>imageIds</code> is the client half of a rule
  <code>image_gallery/gallery.py</code> also implements; the two must agree.
  See <a href="../../../docs/adr/0020-ids-are-derived-in-the-browser.md">ADR 20</a>.
</footer>
</body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-report", action="store_true", help="run without writing HTML")
    parser.add_argument("--node", action="store_true", help="use a local node, not Docker")
    args = parser.parse_args()

    xml_text, exit_code = run_tests(args.node)
    cases = parse(xml_text)

    if not cases:
        print("no test results parsed — the runner produced no JUnit XML:", file=sys.stderr)
        print(xml_text[:2000], file=sys.stderr)
        return exit_code or 1

    coverage = parse_coverage()
    lines_found = sum(f.lines_found for f in coverage)
    overall = 100.0 * sum(f.lines_hit for f in coverage) / lines_found if lines_found else 0.0

    passed = sum(case.passed for case in cases)
    for case in cases:
        if not case.passed:
            print(f"FAIL {case.suite} :: {case.name}\n     {case.failure}", file=sys.stderr)

    print(f"{passed}/{len(cases)} client unit tests passed")
    for f in coverage:
        gaps = f", uncovered {f.uncovered}" if f.uncovered else ""
        print(f"  {f.path}: {f.line_percent:.1f}% lines, {f.branch_percent:.1f}% branches{gaps}")

    if not args.no_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render(cases, coverage), encoding="utf-8")
        print(f"report: {REPORT_PATH.relative_to(REPO_ROOT)}")

    # Coverage gates the build like the Python tier's does. A suite that runs
    # green while leaving code untested reports success it has not earned.
    if coverage and overall < COVERAGE_FLOOR:
        print(
            f"coverage {overall:.1f}% is below the {COVERAGE_FLOOR:.0f}% floor",
            file=sys.stderr,
        )
        return 1

    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
