import os

import pytest

# Base URL of the server the e2e suite drives. Points at the compose-published
# port by default, so `docker compose up -d` followed by
# `pytest -c tests/pytest.ini -m e2e` works with no further configuration.
E2E_BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return E2E_BASE_URL
