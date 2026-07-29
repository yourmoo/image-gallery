"""Checks on the BDD harness itself.

The cold-cache list in tests/e2e/conftest.py names scenarios by their generated
test name. That coupling is invisible: rename a scenario in the feature file and
the entry silently stops matching, so the scenario quietly starts running
against a warm cache and passes for the wrong reason.

This test makes that failure loud. It is a unit test rather than a check inside
the e2e conftest because it must hold regardless of which scenarios a given run
selects.
"""

from __future__ import annotations

import re
from pathlib import Path

# tests/unit/python/ -> tests/
TESTS = Path(__file__).resolve().parents[2]
FEATURES = TESTS / "features"
E2E_CONFTEST = TESTS / "e2e" / "conftest.py"


def _scenario_test_names(feature: Path) -> set[str]:
    """Reproduce pytest-bdd's scenario-title -> test-name conversion."""
    names = set()
    for line in feature.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*Scenario(?: Outline)?:\s*(.+?)\s*$", line)
        if not match:
            continue
        slug = re.sub(r"[^a-z0-9]+", "_", match.group(1).lower()).strip("_")
        names.add(f"test_{slug}")
    return names


def _cold_cache_entries() -> set[str]:
    source = E2E_CONFTEST.read_text(encoding="utf-8")
    block = re.search(r"COLD_CACHE_SCENARIOS\s*=\s*\{(.*?)\}", source, re.S)
    assert block, "COLD_CACHE_SCENARIOS not found in tests/e2e/conftest.py"
    return set(re.findall(r'"([^"]+)"', block.group(1)))


def test_every_cold_cache_entry_names_a_real_scenario():
    """A renamed scenario must not silently drop off the cold-cache list."""
    known = set()
    for feature in FEATURES.glob("*.feature"):
        known |= _scenario_test_names(feature)

    unknown = _cold_cache_entries() - known
    assert not unknown, (
        "COLD_CACHE_SCENARIOS names scenarios that no longer exist "
        f"(renamed in the feature file?): {sorted(unknown)}"
    )
