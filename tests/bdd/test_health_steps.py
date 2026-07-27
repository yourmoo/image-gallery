"""Step definitions for tests/features/health.feature."""

import pytest
from pytest_bdd import given, scenarios, then, when

scenarios("health.feature")


@pytest.fixture
def context() -> dict:
    """Per-scenario bag for carrying state between steps."""
    return {}


@given("the application is running")
def application_is_running(client, context):
    context["client"] = client


@when("I request the health endpoint")
def request_health(context):
    context["response"] = context["client"].get("/healthz")


@when("I request the landing page")
def request_landing(context):
    context["response"] = context["client"].get("/")


@then("the response status is 200")
def status_is_200(context):
    assert context["response"].status_code == 200


@then('the response reports status "ok"')
def reports_ok(context):
    assert context["response"].json()["status"] == "ok"


@then("the page shows the gallery heading")
def shows_heading(context):
    assert b"Image Gallery" in context["response"].content
