import os

import pytest

# Base URL of the server the smoke tests drive.
#
# Defaults to the port `compose.e2e.yaml` publishes, because that is the stack
# the suite starts for itself: tests/e2e/conftest.py brings it up when it is
# not already running. Pointing at 8080 — the ordinary compose.yaml — meant
# these tests failed with a connection refused unless a *second* stack happened
# to be up, which made them look broken whenever the BDD suite was green.
E2E_BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8081")


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return E2E_BASE_URL
