"""`/images/<id>` — the detail page's shell.

A page, not bytes: `/img/<id>` serves those. The two are separate routes
because a user links to and bookmarks the first while an `<img>` element
fetches the second, and one path cannot be both.

The rule this page applies is docs/adr/0007-detail-view-size.md's resolution of
F4.2 against F4.3. Size and filters behave *differently* on the way from grid
to detail:

    size       presentation — forced up, never down
    grayscale  content — carried over untouched
    blur       content — carried over untouched

Neither requirement overrides the other; they were addressing different things.

`detail_size` still lives here because it is the pure rule. What the *page*
reports now comes from `/api/images/<id>`, so those assertions moved to
test_api_image.py with the content
(docs/adr/0022-the-detail-page-joins-the-client.md). What is left below is what
the shell alone still decides.
"""

import pytest
from django.urls import reverse

from image_gallery.detail import detail_size


def url_for(image_id: int) -> str:
    return reverse("detail", args=[image_id])


# --- the size rule (F4.2 vs F4.3) ----------------------------------------


@pytest.mark.parametrize("gallery_size", ["small", "medium", "large"])
def test_a_named_gallery_size_becomes_large(gallery_size):
    """"Larger" is satisfied unconditionally, not in most cases."""
    assert detail_size(gallery_size, large="800x800") == "large"


def test_a_custom_size_smaller_than_large_is_replaced_by_large():
    assert detail_size("300x300", large="800x800") == "large"


def test_a_custom_size_larger_than_large_is_kept():
    """Dropping 1200x900 to 800x800 would make the detail view *smaller* than
    the grid — the precise opposite of what "display a larger version" asks."""
    assert detail_size("1200x900", large="800x800") == "1200x900"


def test_a_custom_size_larger_in_only_one_dimension_is_kept():
    """The rule is "never smaller than the gallery", so either dimension
    exceeding `large` is enough to keep the custom size."""
    assert detail_size("1200x600", large="800x800") == "1200x600"


def test_a_custom_size_exactly_large_is_expressed_as_the_name():
    """Same pixels either way; the name is what the parameters panel shows."""
    assert detail_size("800x800", large="800x800") == "large"


def test_the_comparison_follows_the_configured_large():
    """A deployment can retune what `large` means, and the rule follows it."""
    assert detail_size("900x900", large="1000x1000") == "large"
    assert detail_size("900x900", large="800x800") == "900x900"


# --- the shell -----------------------------------------------------------


def test_the_detail_page_is_html_not_bytes(client):
    response = client.get(url_for(7))

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]


def test_the_shell_carries_the_id_the_script_needs(client):
    """The id is in the path, so the server knows it before any script runs —
    the client never has to parse a URL to find out which image this is."""
    body = client.get(url_for(7)).content.decode()

    assert 'data-image-id="7"' in body


def test_the_shell_reverses_the_api_route(client):
    """No path is written in JavaScript (F5.4): the template reverses the route
    and the script substitutes the id."""
    body = client.get(url_for(7)).content.decode()

    assert f'data-api-url-template="{reverse("api_image", args=[0])}"' in body


def test_the_shell_carries_no_image_data(client):
    """It is a shell. Resolved values arrive from the API, so finding one baked
    into the markup would mean the two could disagree."""
    body = client.get(url_for(7), {"size": "small"}).content.decode()

    assert "size=large" not in body
    assert 'src="/img/' not in body


def test_the_shell_renders_no_notice(client):
    """A scenario asserts the banner is *absent* when there is nothing to say,
    so the client creates it only when the payload carries one."""
    body = client.get(url_for(7), {"blur": "99"}).content.decode()

    assert 'data-testid="notice"' not in body


def test_a_bad_parameter_does_not_redirect(client):
    """It answers 200 and lets the payload explain.

    The old redirect is what produced the crash this change came from: two
    parameters fed the size, the correction dropped only one, and the page
    redirected to itself until the browser gave up. Nothing redirects now, so
    the loop cannot be reintroduced by getting that list wrong again.
    """
    assert client.get(url_for(7), {"blur": "99"}).status_code == 200
    assert client.get(url_for(7), {"custom_detail_size": "3000x1000"}).status_code == 200
    assert client.get(url_for(7), {"detail_size": "enormous"}).status_code == 200


def test_the_controls_exist_in_the_document(client):
    """Server-rendered, like the gallery's: F2.5 wants a real control that
    survives a scripting failure and is visible to a reader of the HTML. Only
    the *values* wait for the payload."""
    body = client.get(url_for(7)).content.decode()

    for testid in ("size-control", "custom-size-control", "grayscale-control", "blur-control"):
        assert f'data-testid="{testid}"' in body


@pytest.mark.parametrize("image_id", [0, 101, 999])
def test_an_image_outside_the_collection_is_not_found(client, image_id):
    """Refused at the document, not in the payload: a bookmark, a crawler and a
    `curl` all need to see the 404, and the id is known before any script runs.

    A bad *parameter* is different — it has a sensible substitute, so it
    recovers (docs/adr/0006-recover-and-explain.md).
    """
    assert client.get(url_for(image_id)).status_code == 404
