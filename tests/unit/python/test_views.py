"""The HTTP layer: what each endpoint returns, and what it refuses to do.

Three properties here are architectural rather than behavioural, and none is
observable through a browser, which is why they are unit tests:

- Serving the shell makes no upstream call
  (docs/adr/0017-image-fetch-timing.md).
- A bad URL is corrected at the document boundary, before the client boots
  (docs/adr/0019-validation-errors-carry-a-usable-payload.md).
- The shell publishes bounds rather than image data
  (docs/adr/0020-ids-are-derived-in-the-browser.md).
"""

import socket
from urllib.parse import parse_qs, urlparse

import pytest
from django.urls import reverse


def query_of(response) -> dict:
    """The query parameters of a redirect's Location header."""
    return parse_qs(urlparse(response["Location"]).query)


def notices_in(response) -> list[str]:
    """The parameter names named by a redirect's notices.

    A notice token is `invalid_<parameter>:<value>`; the value varies with the
    input, so tests assert on the parameter and leave the wording to the
    client, which is where it belongs.
    """
    return [token.split(":", 1)[0] for token in query_of(response).get("notice", [])]


# --- the published bounds (ADR 20) ---------------------------------------


def test_the_shell_publishes_the_bounds_the_client_derives_ids_from(client):
    """The client computes its own id range, so it is handed the bounds.

    Without these the grid cannot be built at all, which is why each is
    asserted rather than checking that "some markup rendered".
    """
    body = client.get(reverse("index")).content.decode()

    assert 'data-page="1"' in body
    assert 'data-count="10"' in body
    assert 'data-catalogue-size="100"' in body


def test_the_published_bounds_follow_the_validated_request(client):
    """Not the raw query string: the client must never be handed a value the
    server would go on to reject."""
    body = client.get(reverse("index"), {"page": "3", "count": "20"}).content.decode()

    assert 'data-page="3"' in body
    assert 'data-count="20"' in body


def test_the_grid_carries_the_size_the_design_system_uses_for_its_cell_floor(client):
    """`data-size` selects the cell width (docs/ui/design-system.md § Image grid)."""
    assert 'data-size="medium"' in client.get(reverse("index")).content.decode()
    assert 'data-size="large"' in client.get(
        reverse("index"), {"size": "large"}
    ).content.decode()


def test_an_invalid_size_never_reaches_the_markup(client):
    """`data-size` feeds a CSS selector, so an unvalidated value must not get
    there. It cannot: a bad size is corrected before anything renders."""
    response = client.get(reverse("index"), {"size": "huge"})

    assert response.status_code == 302
    assert "size=huge" not in response["Location"], "not as a live parameter"
    assert notices_in(response) == ["invalid_size"]


def test_the_shell_publishes_a_reversed_image_url_template(client):
    """F5.2 and F5.4: the client substitutes an id into a server-built URL
    rather than assembling a path of its own. Reversing it here means the route
    can move in urls.py without touching any JavaScript."""
    body = client.get(reverse("index")).content.decode()

    assert f'data-image-url-template="{reverse("image", args=[0])}"' in body


def test_the_shell_renders_a_real_count_control(client):
    """F2.5 says the count is changeable "by the user via UI".

    The requirement most easily under-delivered: a query parameter a test can
    set is not a control. It is server-rendered rather than built by JS so it
    exists before any script runs and cannot be lost to a scripting failure.
    """
    body = client.get(reverse("index")).content.decode()

    assert 'data-testid="count-control"' in body
    assert "<select" in body


def test_the_count_control_offers_exactly_the_configured_allow_list(client):
    """Not a hardcoded 10/20/50: the list is deployment configuration, and the
    control, the validator, and the contract must all read the same one."""
    body = client.get(reverse("index")).content.decode()

    for value in (10, 20, 50):
        assert f'value="{value}"' in body


def test_the_gallery_offers_a_field_for_a_custom_size(client):
    """`WxH` cannot be enumerated in a select, so it gets a field beside one.

    The backend has always accepted custom dimensions (ADR 10) and validated
    them against the configured bounds; without a control the feature was
    reachable only by editing the URL.
    """
    body = client.get(reverse("index")).content.decode()

    assert 'data-testid="custom-size-control"' in body


def test_an_active_custom_size_fills_the_field_rather_than_the_select(client):
    """The form re-renders from the URL, so an active custom size has to be
    visible on load — and it cannot be, in a select that does not list it."""
    body = client.get(reverse("index"), {"size": "640x480"}).content.decode()

    assert 'value="640x480"' in body


def test_the_active_count_is_marked_selected(client):
    """The form is re-rendered from the URL on every navigation, so which value
    is active has to be visible on load (docs/ui/ui-notes.md § States)."""
    body = client.get(reverse("index"), {"count": "20"}).content.decode()

    assert '<option value="20" selected' in body


def test_the_shell_carries_no_image_data(client):
    """Client-side rendering: tiles are built in the browser, not the template."""
    assert "image-tile" not in client.get(reverse("index")).content.decode()


def test_the_shell_carries_no_provider_vocabulary(client):
    """`seed` and the provider's name never reach the browser (ADR 9).

    The id a tile carries *is* the seed, but only the server may know that.
    """
    body = client.get(reverse("index")).content.decode().lower()

    assert "seed" not in body
    assert "picsum" not in body


def test_no_template_comment_leaks_into_the_page(client):
    """`{# #}` is single-line only, so a multi-line one renders as body text.

    That is exactly what happened once: several lines of commentary appeared
    above the grid on every page. Invisible to a status-code assertion and to
    every `data-testid` lookup, because the markup around it stayed correct.
    """
    body = client.get(reverse("index")).content.decode()

    for marker in ("{#", "#}", "{% comment %}", "{% endcomment %}"):
        assert marker not in body, f"template comment syntax {marker!r} reached the page"

    assert "design-system.md" not in body


def test_no_upstream_call_is_made_while_serving_the_shell(client, monkeypatch):
    """Opening a socket at all is a failure.

    Asserting on a mocked HTTP client would only prove that *that* client was
    unused. Failing the connection itself catches any route to the network,
    including one added later by a different module.
    """

    def refuse(*args, **kwargs):
        raise AssertionError("serving the shell must not perform upstream I/O")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    assert client.get(reverse("index")).status_code == 200


# --- recovery at the document boundary (ADR 19) --------------------------


def test_a_valid_request_renders_the_shell(client):
    response = client.get(reverse("index"))

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]


@pytest.mark.parametrize("bad", ["abc", "0", "-5", "999", "1.5"])
def test_a_bad_page_in_the_address_bar_redirects_to_page_one(client, bad):
    """Brief line 48, and the reason the client can be trusted downstream.

    Page 1 is the default, so the corrected URL says nothing about `page` at
    all — the absence *is* page 1. The notice is what proves the correction
    happened.
    """
    response = client.get(reverse("index"), {"page": bad})

    assert response.status_code == 302
    assert "page" not in query_of(response)
    assert notices_in(response) == ["invalid_page"]


@pytest.mark.parametrize("bad", ["7", "0", "-1", "abc"])
def test_a_bad_count_is_corrected_to_the_default(client, bad):
    response = client.get(reverse("index"), {"count": bad})

    assert response.status_code == 302
    assert "count" not in query_of(response), "the default is written as an absence"
    assert notices_in(response) == ["invalid_count"]


def test_a_corrected_url_keeps_a_non_default_value_explicit(client):
    """Only defaults are dropped. A page the user really asked for stays."""
    response = client.get(reverse("index"), {"page": "3", "count": "7"})

    assert query_of(response)["page"] == ["3"]
    assert notices_in(response) == ["invalid_count"]


def test_the_redirect_preserves_parameters_it_did_not_reject(client):
    """One bad parameter must not discard the good ones."""
    response = client.get(reverse("index"), {"page": "abc", "size": "large"})

    assert query_of(response)["size"] == ["large"]
    assert notices_in(response) == ["invalid_page"]


def test_several_invalid_parameters_produce_several_notices(client):
    """`notice` repeats, so the encoder must preserve a repeated key.

    `urllib.parse.urlencode` keeps only the last value of a QueryDict even with
    `doseq=True`, which silently dropped one of the two.
    """
    response = client.get(reverse("index"), {"page": "abc", "count": "7"})

    assert sorted(notices_in(response)) == ["invalid_count", "invalid_page"]


def test_a_valid_request_is_not_redirected(client):
    """A redirect on a good URL would loop."""
    assert client.get(reverse("index"), {"page": "2", "count": "20"}).status_code == 200


def test_the_corrected_url_survives_a_second_pass(client):
    """The redirect target must itself be valid, or the browser loops forever.

    This is the failure mode a redirect-on-invalid design has to rule out, and
    it is cheap to check: follow the redirect and require a single hop.
    """
    response = client.get(reverse("index"), {"page": "abc"}, follow=True)

    assert response.status_code == 200
    assert len(response.redirect_chain) == 1


def test_a_page_valid_only_at_a_larger_count_is_accepted(client):
    """`?count=50&page=2` is in range; at the default count it would not be.

    Guards the ordering inside the validator, through the view that uses it.
    """
    assert client.get(reverse("index"), {"count": "50", "page": "2"}).status_code == 200


# --- health --------------------------------------------------------------


def test_health_answers_without_touching_the_gallery(client, monkeypatch):
    """It must keep answering when the gallery cannot.

    A health check that failed during an upstream outage would have an
    orchestrator restart a container that is working correctly
    (docs/adr/0012-resilience-strategy.md).
    """

    def refuse(*args, **kwargs):
        raise AssertionError("healthz must not perform upstream I/O")

    monkeypatch.setattr(socket.socket, "connect", refuse)

    response = client.get(reverse("healthz"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
