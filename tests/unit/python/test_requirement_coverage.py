"""Every requirement has a scenario, and every scenario names a real requirement.

The link between docs/core-features.md and the Gherkin is a naming convention:
requirement F2.2 is covered by scenarios tagged ``@F2_2``. A convention with
nothing enforcing it drifts -- a requirement gets added with no scenario, or a
scenario is tagged with a requirement that no longer exists, and both failures
are invisible until someone reads all four feature files side by side.

These tests make the convention checkable. They are unit tests, not part of the
e2e tier, because they read files and need no browser or running server.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# tests/unit/python/ -> tests/
TESTS = Path(__file__).resolve().parents[2]
FEATURES = TESTS / "features"
PYTEST_INI = TESTS / "pytest.ini"
CORE_FEATURES = TESTS.parent / "docs" / "core-features.md"

# Requirements deliberately not covered by a scenario, with the reason.
#
# An exemption belongs here only when the requirement is *unobservable from
# outside the application* -- not merely untested yet. Anything observable
# should have Gherkin.
UNCOVERED_BY_DESIGN: dict[str, str] = {
    "F5_1": "code structure: all image generation logic on the backend",
    "F5_2": "code structure: templates never construct image URLs",
    "F5_3": "code structure: URL generation centralised in a service layer",
    "F5_4": "code structure: Django URL reversing for internal links",
}


def _documented_requirements() -> set[str]:
    """Requirement ids from the tables in docs/core-features.md, as F2_2."""
    text = CORE_FEATURES.read_text(encoding="utf-8")
    return {
        f"F{major}_{minor}"
        for major, minor in re.findall(r"^\|\s*F(\d+)\.(\d+)\s*\|", text, re.M)
    }


def _tagged_requirements() -> dict[str, set[str]]:
    """Requirement tag -> the feature files that use it."""
    found: dict[str, set[str]] = {}
    for feature in sorted(FEATURES.glob("*.feature")):
        for tag in re.findall(r"@(F\d+_\d+)\b", feature.read_text(encoding="utf-8")):
            found.setdefault(tag, set()).add(feature.name)
    return found


def _declared_markers() -> set[str]:
    """Markers declared in pytest.ini, which --strict-markers enforces."""
    text = PYTEST_INI.read_text(encoding="utf-8")
    block = re.search(r"^markers\s*=(.*)", text, re.S | re.M)
    assert block, "no markers block in pytest.ini"
    return set(re.findall(r"^\s{4}(\w+):", block.group(1), re.M))


def test_every_documented_requirement_has_a_scenario():
    """A requirement with no scenario is a requirement nobody is testing."""
    documented = _documented_requirements()
    assert documented, "no requirements parsed from core-features.md"

    uncovered = documented - set(_tagged_requirements()) - set(UNCOVERED_BY_DESIGN)

    assert not uncovered, (
        "these requirements have no scenario tagged with them: "
        f"{sorted(uncovered)}. Add a scenario, or record the exemption and its "
        "reason in UNCOVERED_BY_DESIGN."
    )


def test_exemptions_are_still_exempt():
    """An exempted requirement must not quietly acquire a scenario.

    If one does, the exemption is wrong and should be removed rather than left
    to imply the requirement is untestable. Guards against the list rotting into
    a place where inconvenient requirements are parked.
    """
    tagged = set(_tagged_requirements())
    contradicted = sorted(tagged & set(UNCOVERED_BY_DESIGN))

    assert not contradicted, (
        f"{contradicted} are listed in UNCOVERED_BY_DESIGN but now have "
        "scenarios. Remove them from the exemption list."
    )


def test_every_scenario_tag_names_a_documented_requirement():
    """Catches a typo'd tag, and a requirement removed from the docs."""
    documented = _documented_requirements()
    tagged = _tagged_requirements()

    unknown = {tag: files for tag, files in tagged.items() if tag not in documented}

    assert not unknown, (
        "these scenario tags do not match any requirement in core-features.md: "
        f"{ {k: sorted(v) for k, v in unknown.items()} }"
    )


def test_every_requirement_tag_is_declared_in_pytest_ini():
    """--strict-markers fails the run on an undeclared tag.

    Checked here as well so the failure names the missing marker, rather than
    surfacing as an unrelated collection error in the e2e tier.
    """
    undeclared = set(_tagged_requirements()) - _declared_markers()

    assert not undeclared, (
        f"these tags are used but not declared in pytest.ini: {sorted(undeclared)}"
    )


def test_every_scenario_carries_a_build_stage():
    """Each scenario belongs to exactly one stage of the build order.

    The stages encode dependency: a scenario in stage N relies only on stages
    before it, which is what makes `-m stage1` a runnable slice rather than an
    arbitrary subset. A scenario with no stage has no place in the sequence; one
    with two is ambiguous about when it can first pass.

    health.feature is exempt -- it tests the baseline harness, not a gallery
    requirement, and predates the build order entirely.
    """
    problems = []
    for feature in sorted(FEATURES.glob("*.feature")):
        if feature.name == "health.feature":
            continue

        pending: list[str] = []
        for line in feature.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("@"):
                pending = re.findall(r"@(stage\d+)\b", stripped)
            elif re.match(r"Scenario(?: Outline)?:", stripped):
                title = stripped.split(":", 1)[1].strip()
                if len(pending) != 1:
                    problems.append(
                        f"{feature.name}: {title!r} has {len(pending)} stage tags"
                    )
                pending = []

    assert not problems, "\n".join(problems)


# Tags that describe what a scenario covers when it is not an F-requirement.
# `resilience` is the matrix from docs/adr/0012-resilience-strategy.md: failure
# handling is specified by an ADR rather than by a numbered brief requirement,
# but it is fully observable and so belongs in Gherkin.
NON_REQUIREMENT_SUBJECTS = {"resilience"}


@pytest.mark.parametrize("feature", sorted(FEATURES.glob("*.feature")), ids=lambda p: p.name)
def test_every_scenario_declares_what_it_covers(feature: Path):
    """Every scenario says what it is for -- a requirement or a named subject.

    A scenario with only a stage tag says when it can be built but never why it
    exists, which is the state that lets an obsolete scenario survive a change
    in the requirements.
    """
    if feature.name == "health.feature":
        pytest.skip("health.feature tests the harness, not a requirement")

    problems, pending = [], []
    for line in feature.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("@"):
            pending = re.findall(r"@(\w+)\b", stripped)
        elif re.match(r"Scenario(?: Outline)?:", stripped):
            subjects = [
                tag
                for tag in pending
                if re.fullmatch(r"F\d+_\d+", tag) or tag in NON_REQUIREMENT_SUBJECTS
            ]
            if not subjects:
                problems.append(stripped.split(":", 1)[1].strip())
            pending = []

    assert not problems, (
        f"{feature.name} scenarios declaring no requirement or subject: {problems}"
    )
