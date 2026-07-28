"""Step definitions for tests/features/health.feature.

Driven through Playwright against a running server, like every other feature
file. The health endpoint and the application shell could be checked in-process
with the Django test client — neither involves JavaScript — but keeping all
Gherkin in one tier means one scenario report and one place to look. Two extra
browser tests is a negligible cost against that.

See docs/adr/0015-test-strategy.md.
"""

import pytest
from pytest_bdd import given, scenarios, then, when

pytestmark = pytest.mark.e2e

scenarios("health.feature")


@pytest.fixture
def scenario_state() -> dict:
    """Per-scenario bag for carrying state between steps.

    Deliberately not named ``context``: pytest-playwright already defines a
    ``context`` fixture for the browser context, and shadowing it breaks the
    ``page`` fixture that depends on it.
    """
    return {}


@given("the application is running")
def application_is_running(page, e2e_base_url, scenario_state):
    scenario_state["page"] = page
    scenario_state["base_url"] = e2e_base_url


@when("I request the health endpoint")
def request_health(scenario_state):
    """Fetched via the API client: the endpoint returns JSON, not a document."""
    scenario_state["response"] = scenario_state["page"].request.get(
        f"{scenario_state['base_url']}/healthz"
    )


@when("I request the landing page")
def request_landing(scenario_state):
    scenario_state["response"] = scenario_state["page"].goto(scenario_state["base_url"])


@then("the response status is 200")
def status_is_200(scenario_state):
    assert scenario_state["response"].status == 200


@then('the response reports status "ok"')
def reports_ok(scenario_state):
    assert scenario_state["response"].json()["status"] == "ok"


@then("the page shows the gallery heading")
def shows_heading(scenario_state):
    assert "Image Gallery" in scenario_state["page"].title()
