"""Deployment smoke checks: does the container serve a working page?

This tier is deliberately thin. Behaviour — pagination, filters, validation —
is verified by the BDD suite through the Django test client, which is faster and
needs no server. Anything that could pass there does not belong here.

What justifies a browser: **the test client never fetches subresources.** It
renders templates in-process, so a broken `{% static %}` path or a mis-collected
asset leaves the DOM intact and the test green while the page is broken for a
user. See tests/README.md for the incident that established this.

These run against an already-running server (compose or `runserver`), so they
are marked `e2e` and excluded from the default run:

    pytest -c tests/pytest.ini -m e2e
"""

import pytest

pytestmark = pytest.mark.e2e


def test_landing_page_loads(page, e2e_base_url):
    """The shipped image serves a gallery, not the baseline placeholder.

    This asserted on `data-testid="status"` — the "features are not implemented
    yet" paragraph the baseline rendered. Now that the grid is real, checking
    for the grid is what proves the deployment serves the application rather
    than an empty shell.
    """
    page.goto(e2e_base_url)

    assert page.get_by_test_id("gallery").is_visible()
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
