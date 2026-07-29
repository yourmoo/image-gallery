"""Run a test tier and write its reports.

One entry point per tier, so **no report path is ever typed by hand**. That is
the point of this file rather than a convenience: the paths used to live as
prose in four README commands, and when `tests/reports/` was reorganised the old
commands kept writing to the old places, leaving orphaned directories that
looked current. Paths belong in code that can be changed once.

    python tests/run.py python      Django modules and views, with coverage
    python tests/run.py js          the client's pure logic, with coverage
    python tests/run.py e2e         Gherkin scenarios in a real browser
    python tests/run.py all         every tier, in that order

Anything after `--` is passed through to the underlying runner:

    python tests/run.py python -- -k validation -x
    python tests/run.py e2e -- -m stage1

Each tier writes only its own directory, and `--clean` empties that directory
first so a deleted test cannot leave a stale report behind.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS = REPO_ROOT / "tests" / "reports"

# The single source of truth for where each tier reports. Anything that needs a
# report path reads it from here.
PYTHON_REPORTS = REPORTS / "unit" / "python"
JS_REPORTS = REPORTS / "unit" / "js"
E2E_REPORTS = REPORTS / "e2e"

PYTEST_INI = "tests/pytest.ini"


def _python(*args: str) -> list[str]:
    """The interpreter running this script, so the venv is inherited."""
    return [sys.executable, *args]


def _run(command: list[str]) -> int:
    print(f"\n$ {' '.join(command)}\n", flush=True)
    return subprocess.run(command, cwd=REPO_ROOT).returncode


def _clean(directory: Path) -> None:
    """Empty a tier's report directory.

    Deliberately scoped to one tier's own directory: a run that cleaned the
    whole of `tests/reports/` would delete the other tiers' output, which is
    how you end up unable to compare a failing run against a passing one.
    """
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)


# Paths that a previous layout wrote to and nothing writes to now. Left behind,
# they read as current output — `reports/js/` in particular sits beside `unit/`
# as though it were a third tier. Removed on any `--clean` so the tree cannot
# keep describing a structure that no longer exists.
STALE = [
    REPORTS / "js",
    REPORTS / "unit" / "htmlcov",
    REPORTS / "unit" / "report.html",
]


def _remove_stale() -> None:
    for path in STALE:
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        print(f"removed stale report path: {path.relative_to(REPO_ROOT)}")


def run_python(extra: list[str], clean: bool) -> int:
    """The Django unit tier: modules and views, measured by coverage."""
    if clean:
        _clean(PYTHON_REPORTS)

    return _run(
        _python(
            "-m", "pytest", "-c", PYTEST_INI, "-m", "not e2e",
            f"--html={(PYTHON_REPORTS / 'report.html').relative_to(REPO_ROOT).as_posix()}",
            "--self-contained-html",
            "--cov", "--cov-config=tests/.coveragerc",
            f"--cov-report=html:{(PYTHON_REPORTS / 'htmlcov').relative_to(REPO_ROOT).as_posix()}",
            "--cov-report=term-missing",
            *extra,
        )
    )


def run_js(extra: list[str], clean: bool) -> int:
    """The client unit tier, which owns its own paths in js_tests.py."""
    if clean:
        _clean(JS_REPORTS)

    return _run(_python("tests/js_tests.py", *extra))


def run_e2e(extra: list[str], clean: bool) -> int:
    """The behavioural tier. Needs the compose stack; conftest starts it if not up.

    `--no-cov` is deliberate — the browser drives Django in a container that the
    in-process coverage tool cannot see, so a coverage figure from this tier
    would be misleading rather than merely absent
    (docs/adr/0015-test-strategy.md).
    """
    if clean:
        _clean(E2E_REPORTS)

    cucumber = (E2E_REPORTS / "cucumber.json").relative_to(REPO_ROOT).as_posix()
    code = _run(
        _python(
            "-m", "pytest", "-c", PYTEST_INI, "-m", "e2e", "--no-cov",
            f"--html={(E2E_REPORTS / 'report.html').relative_to(REPO_ROOT).as_posix()}",
            "--self-contained-html",
            f"--cucumber-json={cucumber}",
            *extra,
        )
    )

    # Rendered even when scenarios failed: a failing run is exactly when the
    # Given/When/Then breakdown is worth reading.
    if (E2E_REPORTS / "cucumber.json").exists():
        _run(
            _python(
                "tests/cucumber_html.py",
                cucumber,
                (E2E_REPORTS / "scenarios.html").relative_to(REPO_ROOT).as_posix(),
            )
        )

    return code


TIERS = {"python": run_python, "js": run_js, "e2e": run_e2e}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tier", choices=[*TIERS, "all"], help="which tier to run")
    parser.add_argument(
        "--clean", action="store_true", help="empty the tier's report directory first"
    )
    parser.add_argument(
        "extra", nargs="*", help="arguments passed through to the underlying runner"
    )
    args = parser.parse_args()

    tiers = list(TIERS) if args.tier == "all" else [args.tier]

    if args.extra and len(tiers) > 1:
        sys.exit("pass-through arguments need a single tier, not 'all'")

    if args.clean:
        _remove_stale()

    results = {tier: TIERS[tier](args.extra, args.clean) for tier in tiers}

    if len(results) > 1:
        print("\n" + "-" * 46)
        for tier, code in results.items():
            print(f"  {tier:8} {'passed' if code == 0 else f'FAILED ({code})'}")
        print("-" * 46)

    return max(results.values())


if __name__ == "__main__":
    sys.exit(main())
