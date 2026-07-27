"""End-to-end browser tests for the health endpoint and landing page.

These run against an already-running server (compose or `runserver`), not the
Django test client, so they are marked `e2e` and excluded from the default run:

    pytest -c tests/pytest.ini -m e2e
"""

import pytest

pytestmark = pytest.mark.e2e


def test_landing_page_loads(page, e2e_base_url):
    page.goto(e2e_base_url)

    assert page.get_by_test_id("status").is_visible()
    assert "Image Gallery" in page.title()


def test_health_endpoint_is_reachable(page, e2e_base_url):
    response = page.request.get(f"{e2e_base_url}/healthz")

    assert response.status == 200
    assert response.json()["status"] == "ok"


def test_landing_page_loads_every_subresource(page, e2e_base_url):
    """No request made by the page may fail.

    Asserting on rendered content alone is not enough: a missing stylesheet or
    script still leaves the DOM intact, so the page looks fine to a test while
    being broken for a user. This caught a real 404 on the stylesheet, which
    gunicorn served only because WhiteNoise was added — Django's own staticfiles
    handler is inactive when DEBUG is off.
    """
    failures = []

    def record(response):
        if response.status >= 400:
            failures.append(f"{response.status} {response.url}")

    page.on("response", record)
    page.goto(e2e_base_url, wait_until="networkidle")

    assert failures == []


def test_landing_page_stylesheet_is_served(page, e2e_base_url):
    """The stylesheet resolves and is actually CSS, not an error page."""
    page.goto(e2e_base_url)
    href = page.get_attribute("link[rel=stylesheet]", "href")

    assert href, "landing page declares no stylesheet"

    response = page.request.get(f"{e2e_base_url}{href}")

    assert response.status == 200
    assert "text/css" in response.headers["content-type"]
