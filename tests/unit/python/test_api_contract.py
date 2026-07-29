"""The documented API contract must match the application that serves it.

`docs/api-contract.md` is written by hand, which normally means it is true when
written and decays silently from the first change. These tests are what stop
that: the Endpoints table is parsed and diffed against the URLconf, so adding,
removing, or renaming a route without updating the document fails the build.

This is the same approach as `test_only_settings_reads_the_environment` — a
documented rule with no test decays at the first deadline
(docs/adr/0008-configuration-in-settings.md).
"""

import re
from pathlib import Path

import pytest
from django.urls import get_resolver, reverse

import image_gallery

CONTRACT_PATH = (
    Path(image_gallery.__file__).resolve().parent.parent / "docs" / "api-contract.md"
)

# Routes that exist but are deliberately absent from the contract. Empty by
# design: an undocumented endpoint should be a decision, not an oversight.
UNDOCUMENTED_BY_DESIGN: set[str] = set()


def _documented_routes() -> dict[str, str]:
    """Parse the Endpoints table into {route name: path}.

    Only the **first table** under `## Endpoints` is read, and reading stops at
    the blank line that ends it. Scanning to the next heading instead would
    swallow any other table in the section — the `index` description carries one
    describing its data attributes — and silently treat its rows as routes.

    The "Planned endpoints" table is excluded for a different reason: those
    routes are specified but not yet served, so enforcing them would fail the
    build for work not yet started.
    """
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    section = text.split("## Endpoints", 1)[1].split("## Planned endpoints", 1)[0]

    routes = {}
    for line in section.splitlines():
        stripped = line.strip()
        if routes and not stripped.startswith("|"):
            break  # the table ended; anything further is prose or another table
        # | `name` | `/path` | GET | ... |
        match = re.match(r"\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|", stripped)
        if match:
            routes[match.group(1)] = match.group(2)

    return routes


def _routed_names() -> set[str]:
    """Every named route in the URLconf."""
    return {
        pattern.name
        for pattern in get_resolver().url_patterns
        if getattr(pattern, "name", None)
    }


def test_the_contract_table_is_parseable():
    """Guards the parsing the other tests depend on.

    Without this, a formatting change could silently empty the table and make
    every comparison below trivially pass.
    """
    documented = _documented_routes()

    assert documented, "no rows parsed from the Endpoints table"
    assert all(path.startswith("/") for path in documented.values())


def test_every_documented_route_exists():
    """A documented endpoint that is not routed is a promise nothing keeps."""
    missing = [name for name in _documented_routes() if name not in _routed_names()]

    assert missing == [], f"documented but not routed: {missing}"


def test_every_route_is_documented():
    """Adding an endpoint without documenting it fails here."""
    undocumented = _routed_names() - set(_documented_routes()) - UNDOCUMENTED_BY_DESIGN

    assert undocumented == set(), (
        f"routed but undocumented: {sorted(undocumented)}. "
        f"Add them to the Endpoints table in {CONTRACT_PATH.name}."
    )


@pytest.mark.parametrize("name,documented_path", sorted(_documented_routes().items()))
def test_documented_path_matches_the_urlconf(name, documented_path):
    """The path a reader would use is the path the application serves."""
    assert reverse(name) == documented_path


def test_documented_responses_match_what_is_served(client):
    """Content types in the table are what the endpoints actually return."""
    expected = {
        "index": "text/html",
        "healthz": "application/json",
    }

    for name, content_type in expected.items():
        response = client.get(reverse(name))

        assert response.status_code == 200
        assert content_type in response["Content-Type"]


def test_health_payload_matches_the_documented_shape(client):
    """The documented body is the body served."""
    payload = client.get(reverse("healthz")).json()

    assert payload == {"status": "ok"}


def test_contract_does_not_leak_provider_vocabulary():
    """`seed` and the provider's name are internal to the service layer.

    Client URLs must survive a provider change, so provider terms must not
    appear in the published contract — docs/adr/0009-url-vocabularies.md.
    """
    text = CONTRACT_PATH.read_text(encoding="utf-8").lower()

    # The Vocabulary section names them in order to rule them out, so check the
    # parts of the document that describe endpoints and parameters.
    described = text.split("## vocabulary", 1)[0]

    assert "picsum" not in described
    assert "seed" not in described
