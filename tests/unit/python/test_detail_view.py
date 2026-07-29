"""`/images/<id>` — the detail page.

A page, not bytes: `/img/<id>` serves those. The two are separate routes
because a user links to and bookmarks the first while an `<img>` element
fetches the second, and one path cannot be both.

The rule this view exists to apply is docs/adr/0007-detail-view-size.md's
resolution of F4.2 against F4.3. Size and filters behave *differently* on the
way from grid to detail:

    size       presentation — forced up, never down
    grayscale  content — carried over untouched
    blur       content — carried over untouched

Neither requirement overrides the other; they were addressing different things.
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


# --- the page ------------------------------------------------------------


def test_the_detail_page_is_html_not_bytes(client):
    response = client.get(url_for(7))

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]


def test_the_detail_page_shows_the_image_at_large(client):
    """The <img> points at the proxy, at the size this view resolved."""
    body = client.get(url_for(7)).content.decode()

    assert 'data-testid="detail-image"' in body
    assert "size=large" in body


def test_a_custom_size_larger_than_large_reaches_the_image(client):
    body = client.get(url_for(7), {"size": "1200x900"}).content.decode()

    assert "size=1200x900" in body


def test_filters_carry_over_untouched(client):
    """F4.3 — unlike size, these describe how the image should look anywhere."""
    body = client.get(url_for(7), {"grayscale": "1", "blur": "4"}).content.decode()

    assert "grayscale=1" in body
    assert "blur=4" in body


def test_the_page_carries_no_provider_vocabulary(client):
    body = client.get(url_for(7)).content.decode().lower()

    assert "seed" not in body
    assert "picsum" not in body


@pytest.mark.parametrize("image_id", [101, 999, 0])
def test_an_image_outside_the_collection_is_not_found(client, image_id):
    assert client.get(url_for(image_id)).status_code == 404


def test_an_invalid_parameter_is_corrected_rather_than_refused(client):
    """The detail page is a document, so it recovers like the shell does —
    a pasted URL with a bad blur should still show the image."""
    response = client.get(url_for(7), {"blur": "99"})

    assert response.status_code == 302
    assert "notice=invalid_blur" in response["Location"]


def test_the_corrected_page_explains_what_was_rejected(client):
    """Rendered server-side, unlike the gallery's.

    The gallery builds its banner in JavaScript because the grid is built there
    anyway; this page is server-rendered, so a script here would exist only to
    move markup the template could emit directly — and it would leave the
    explanation missing for the moment before the script ran.
    """
    body = client.get(url_for(7), {"notice": "invalid_blur:99"}).content.decode()

    assert 'data-testid="notice"' in body
    assert "99" in body


def test_a_page_with_nothing_to_explain_renders_no_notice(client):
    """Absence, not an empty banner: the scenario asserting no message is
    shown counts elements."""
    assert 'data-testid="notice"' not in client.get(url_for(7)).content.decode()


def test_an_unrecognised_notice_token_is_ignored(client):
    """A hand-edited URL must not put arbitrary text on the page."""
    body = client.get(url_for(7), {"notice": "<script>alert(1)</script>"}).content.decode()

    assert 'data-testid="notice"' not in body
    assert "alert(1)" not in body


# --- the parameters panel (F4.4) -----------------------------------------


def test_the_panel_reports_the_resolved_values_not_the_requested_ones(client):
    """The honesty burden of ADR 7: this view silently changes the user's size,
    and the panel showing `large` is what keeps that from being a surprise."""
    body = client.get(url_for(7), {"size": "small"}).content.decode()

    assert 'data-testid="param-size"' in body
    assert ">large<" in body.replace(" ", "").replace("\n", "")


def test_the_panel_identifies_the_image_in_client_vocabulary(client):
    """"Image 7", never "seed 7" — ADR 9."""
    body = client.get(url_for(7)).content.decode()

    assert 'data-testid="param-id"' in body
    assert "7" in body


def test_the_panel_reports_both_filters(client):
    body = client.get(url_for(7), {"grayscale": "1", "blur": "4"}).content.decode()

    assert 'data-testid="param-grayscale"' in body
    assert 'data-testid="param-blur"' in body


# --- the panel as a control surface (ADR 7, amended) ---------------------


def test_the_panel_offers_a_control_for_every_value_it_reports(client):
    """F4.4 as amended: the panel reports *and* sets.

    A value shown in a control the user can operate is more discoverable than
    the same value shown as static text — changing it demonstrates what it
    means. That is why the amendment strengthens the honesty burden ADR 7
    placed on this panel rather than weakening it.
    """
    body = client.get(url_for(7)).content.decode()

    assert 'data-testid="size-control"' in body
    assert 'data-testid="grayscale-control"' in body
    assert 'data-testid="blur-control"' in body


def test_the_size_control_offers_every_named_size_including_smaller_ones(client):
    """The page opens at `large`, but the user may choose down from there.

    That is the amendment: brief line 71 is satisfied by what the application
    does on arrival, not by refusing the user a smaller image afterwards.
    """
    body = client.get(url_for(7)).content.decode()

    for name in ("small", "medium", "large"):
        assert f'value="{name}"' in body


def test_a_size_chosen_here_is_honoured_rather_than_forced_up(client):
    """The distinction the amendment turns on.

    Arriving from a `small` gallery still gives `large` — that is the default.
    Asking for `small` *on this page* is a choice, and is obeyed.
    """
    body = client.get(url_for(7), {"detail_size": "small"}).content.decode()

    assert "size=small" in body


def test_the_panel_reports_the_size_chosen_here(client):
    """Report and control must agree after a change, not only on arrival."""
    body = client.get(url_for(7), {"detail_size": "small"}).content.decode()

    assert 'data-testid="param-size"' in body
    assert ">small<" in body.replace(" ", "").replace("\n", "")


def test_arriving_without_a_choice_still_opens_large(client):
    """The default, and every reason for it, is unchanged."""
    body = client.get(url_for(7), {"size": "small"}).content.decode()

    assert "size=large" in body


def test_a_size_chosen_here_does_not_reach_the_back_link(client):
    """A choice made on this page belongs to this page.

    Otherwise opening one image at `small` would silently re-render the whole
    grid on return — a change the user never asked for.

    Asserts on the back link's own href rather than on the page as a whole:
    `small` legitimately appears elsewhere, as an option in the size control.
    """
    import re

    body = client.get(
        url_for(7), {"size": "large", "detail_size": "small"}
    ).content.decode()

    back = re.search(r'data-testid="back-to-gallery" href="([^"]+)"', body)
    assert back, "no back link found"

    assert "size=large" in back.group(1), "the back link keeps the gallery's size"
    assert "small" not in back.group(1), "and not the one chosen on this page"


def test_an_invalid_choice_here_recovers_like_any_other(client):
    response = client.get(url_for(7), {"detail_size": "enormous"})

    assert response.status_code == 302
    assert "notice=invalid_size" in response["Location"]


# --- the way back --------------------------------------------------------


def test_the_back_link_restores_the_page_and_the_filters(client):
    """F4.1. The tile link carried this state here; the back link returns it,
    so the round trip preserves where the user was."""
    body = client.get(
        url_for(7), {"page": "3", "size": "small", "grayscale": "1", "blur": "4"}
    ).content.decode()

    assert 'data-testid="back-to-gallery"' in body
    assert "page=3" in body
    assert "size=small" in body, "the *gallery's* size, not the detail view's"