"""`/api/images/<id>` — the detail page's content, as JSON.

These assertions used to be made against server-rendered HTML in
test_detail_view.py. They moved here with the content
(docs/adr/0022-the-detail-page-joins-the-client.md): the page is now a shell,
so what it *says* is a property of this payload, and probing markup for
`"size=large" in body` was only ever a proxy for asking the server what size it
resolved.

The endpoint's own reason to exist is ADR 7's substitution: it reports
**resolved** values, which the client cannot derive from the URL it was opened
with.
"""

import json

import pytest
from django.test import override_settings
from django.urls import reverse


def url_for(image_id: int) -> str:
    return reverse("api_image", args=[image_id])


def payload(client, image_id: int = 7, **params) -> dict:
    response = client.get(url_for(image_id), params)
    assert response.status_code == 200
    return json.loads(response.content)


# --- the resolved size ---------------------------------------------------


def test_the_endpoint_answers_json(client):
    response = client.get(url_for(7))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"


def test_an_image_opens_at_large_by_default(client):
    """ADR 7: the detail view is never smaller than the gallery."""
    assert payload(client)["size"] == "large"


def test_arriving_from_a_small_gallery_still_opens_large(client):
    """The forced substitution — and the reason this endpoint exists, since the
    client cannot work this out from `?size=small`."""
    assert payload(client, size="small")["size"] == "large"


def test_a_custom_size_larger_than_large_is_kept(client):
    """Opening an image from a 1200x900 grid must not shrink it to 800x800."""
    body = payload(client, size="1200x900")

    assert body["size"] == "1200x900"
    assert "size=1200x900" in body["url"]


def test_a_size_chosen_here_is_honoured_rather_than_forced_up(client):
    assert payload(client, detail_size="small")["size"] == "small"


def test_a_custom_size_wins_over_the_select(client):
    """When both carry a value, the field is the more specific intent — it is
    the one the user typed."""
    body = payload(client, detail_size="large", custom_detail_size="300x300")

    assert body["size"] == "300x300"


def test_an_empty_custom_size_does_not_override_the_selected_one(client):
    """A browser submits every control, so the empty one must not win."""
    response = client.get(url_for(7), {"detail_size": ["small", ""]})

    assert json.loads(response.content)["size"] == "small"


def test_a_custom_size_is_reported_for_the_field(client):
    """A select cannot display a value it does not list, so the field carries
    it and the readout reports it."""
    body = payload(client, custom_detail_size="300x300")

    assert body["customSize"] == "300x300"


def test_a_named_size_leaves_the_custom_field_empty(client):
    assert payload(client, detail_size="small")["customSize"] == ""


# --- filters -------------------------------------------------------------


def test_filters_carry_over_untouched(client):
    """ADR 7 forces the size up; it does not touch the filters."""
    body = payload(client, grayscale="1", blur="4")

    assert body["grayscale"] is True
    assert body["blur"] == 4
    assert "grayscale=1" in body["url"]
    assert "blur=4" in body["url"]


def test_the_url_omits_defaults(client):
    """Keeps the browser and server caches keyed on the same small set of
    variations rather than on URLs differing only in redundant text."""
    url = payload(client)["url"]

    assert "grayscale" not in url
    assert "blur" not in url


# --- what the payload must never contain ---------------------------------


def test_the_payload_carries_no_provider_vocabulary(client):
    """The boundary of ADR 9 holds regardless of the format the answer travels
    in: the client never learns picsum.dev exists."""
    body = json.dumps(payload(client, grayscale="1", blur="4"))

    assert "seed" not in body
    assert "picsum" not in body


def test_the_image_url_points_at_this_application(client):
    assert payload(client)["url"].startswith(reverse("image", args=[7])[:5])


# --- notices -------------------------------------------------------------


def test_nothing_rejected_means_no_notices(client):
    assert payload(client)["notices"] == []


def test_a_rejected_parameter_is_explained(client):
    [notice] = payload(client, blur="99")["notices"]

    assert notice["code"] == "invalid_blur"
    assert notice["value"] == "99"
    assert "99" in notice["message"]


def test_an_out_of_bounds_custom_size_recovers_and_explains_in_one_response(client):
    """The original crash, at its root.

    A rejected custom size used to redirect to a corrected URL that still
    carried the rejected value, so the page redirected to itself until the
    browser gave up. There is no redirect now: the fallback and the explanation
    arrive together, so the loop cannot exist.
    """
    body = payload(client, custom_detail_size="3000x1000")

    assert body["size"] == "large", "falls back to the ADR 7 default"
    [notice] = body["notices"]
    assert notice["code"] == "invalid_size"
    assert notice["value"] == "3000x1000"


def test_the_message_quotes_the_configured_bounds(client):
    """The sentence has to say what *would* work. It reads the live setting, so
    retuning the ceiling cannot leave the wording lying about it."""
    [notice] = payload(client, custom_detail_size="3000x1000")["notices"]

    assert "1600" in notice["message"]
    assert "16" in notice["message"]


@override_settings(GALLERY_MAX_DIMENSION=900)
def test_the_message_follows_a_retuned_ceiling(client):
    [notice] = payload(client, custom_detail_size="3000x1000")["notices"]

    assert "900" in notice["message"]


def test_the_message_never_claims_a_size_it_did_not_apply(client):
    """It used to end "— showing medium." on a page that shows large: one
    hardcoded fallback serving two views with different defaults."""
    [notice] = payload(client, custom_detail_size="3000x1000")["notices"]

    assert "medium" not in notice["message"].split("Pick")[0]


def test_several_rejections_are_all_reported(client):
    codes = {n["code"] for n in payload(client, blur="99", size="huge")["notices"]}

    assert codes == {"invalid_blur", "invalid_size"}


# --- the way back --------------------------------------------------------


def test_the_back_link_restores_the_page_and_the_filters(client):
    back = payload(client, page="3", size="small", grayscale="1")["backUrl"]

    assert "page=3" in back
    assert "size=small" in back
    assert "grayscale=1" in back


def test_the_back_link_keeps_the_gallerys_size_not_this_pages(client):
    """Returning to a grid rendered at large when the user left one rendered at
    small would be a change they never asked for."""
    body = payload(client, size="small")

    assert body["size"] == "large", "the page itself is forced up"
    assert "size=small" in body["backUrl"], "the gallery's size is what returns"


def test_a_size_chosen_here_does_not_reach_the_back_link(client):
    assert "small" not in payload(client, detail_size="small")["backUrl"]


def test_an_unfiltered_gallery_gets_a_clean_back_link(client):
    assert payload(client)["backUrl"] == reverse("index")


# --- the catalogue bound -------------------------------------------------


@pytest.mark.parametrize("image_id", [0, 101, 999])
def test_an_image_outside_the_collection_is_not_found(client, image_id):
    """No sensible substitute exists for an id that cannot be, so this refuses
    rather than recovering."""
    assert client.get(url_for(image_id)).status_code == 404


# --- what the controls need ----------------------------------------------


def test_the_payload_offers_every_named_size(client):
    assert payload(client)["namedSizes"] == ["small", "medium", "large"]


def test_the_payload_carries_the_blur_ceiling(client):
    """The slider's max comes from configuration, so the control cannot offer a
    value the validator would reject."""
    assert payload(client)["maxBlur"] == 10
