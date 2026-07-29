"""Validation is pure, so these tests need no Django and no request.

The rules here are shared by both entry points — the shell view's redirect and
the image endpoints' 400 — so a gap in this file is a gap in both
(docs/adr/0019-validation-errors-carry-a-usable-payload.md).

Only `page` and `count` are validated at stage 1. `size`, `grayscale`, and
`blur` arrive with the stages that render them.
"""

import pytest

from image_gallery.validation import (
    total_pages,
    validate,
    validate_blur,
    validate_count,
    validate_grayscale,
    validate_page,
    validate_size,
)

PAGE_SIZES = (10, 20, 50)
SIZE_BOUNDS = {"minimum": 16, "maximum": 1600}


# --- size ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["small", "medium", "large"])
def test_the_three_named_sizes_are_accepted(name):
    """F3.1. The names are client vocabulary; pixels are resolved later."""
    size, rejection = validate_size(name, default="medium", **SIZE_BOUNDS)

    assert size == name
    assert rejection is None


def test_an_absent_size_takes_the_default():
    size, rejection = validate_size(None, default="medium", **SIZE_BOUNDS)

    assert size == "medium"
    assert rejection is None


@pytest.mark.parametrize("raw", ["", "  "])
def test_a_supplied_but_empty_size_is_a_rejection(raw):
    size, rejection = validate_size(raw, default="medium", **SIZE_BOUNDS)

    assert size == "medium"
    assert rejection is not None


@pytest.mark.parametrize("raw", ["640x480", "1600x1600", "16x16", "200X300"])
def test_custom_pixel_dimensions_are_a_first_class_size(raw):
    """ADR 10 — `WxH` is not a special case, and the X may be either case."""
    size, rejection = validate_size(raw, default="medium", **SIZE_BOUNDS)

    assert size == raw.lower()
    assert rejection is None


@pytest.mark.parametrize("raw", ["6000x6000", "1601x100", "8x8", "0x0"])
def test_dimensions_outside_the_bounds_are_rejected_not_clamped(raw):
    """Silently serving 1600 when 6000 was asked for would be undetectable to
    the caller (docs/adr/0010-configurable-and-custom-sizes.md). picsum does
    not enforce its own documented limit, so this ceiling is the only thing
    bounding upstream traffic.
    """
    size, rejection = validate_size(raw, default="medium", **SIZE_BOUNDS)

    assert size == "medium"
    assert rejection is not None
    assert rejection.parameter == "size"


@pytest.mark.parametrize("raw", ["huge", "enormous", "400", "x", "400x", "axb", "-4x-4"])
def test_a_size_that_is_neither_a_name_nor_a_dimension_pair_is_rejected(raw):
    size, rejection = validate_size(raw, default="medium", **SIZE_BOUNDS)

    assert size == "medium"
    assert rejection is not None


def test_a_rejected_size_names_what_is_accepted():
    _, rejection = validate_size("huge", default="medium", **SIZE_BOUNDS)

    assert "small" in rejection.accepted
    assert "1600" in rejection.accepted, "the bound should be discoverable"


# --- count ---------------------------------------------------------------


def test_an_absent_count_takes_the_default_without_complaint():
    """An unsupplied parameter is the default working as intended.

    Reporting it would put a notice on every first visit to the gallery.
    """
    count, rejection = validate_count(None, allowed=PAGE_SIZES, default=10)

    assert count == 10
    assert rejection is None


@pytest.mark.parametrize("raw", ["", "   "])
def test_a_supplied_but_empty_count_is_a_rejection(raw):
    """Same distinction as `page`: supplied-but-unusable is not absent."""
    count, rejection = validate_count(raw, allowed=PAGE_SIZES, default=10)

    assert count == 10
    assert rejection is not None
    assert rejection.parameter == "count"


@pytest.mark.parametrize("raw,expected", [("10", 10), ("20", 20), ("50", 50)])
def test_allow_listed_counts_are_accepted(raw, expected):
    count, rejection = validate_count(raw, allowed=PAGE_SIZES, default=10)

    assert count == expected
    assert rejection is None


@pytest.mark.parametrize("raw", ["7", "0", "-10", "abc", "10.5", "1e1"])
def test_a_count_outside_the_allow_list_falls_back_and_is_reported(raw):
    """Includes forms that parse as numbers but are not offered.

    `10.5` and `1e1` matter: both are meaningful to a lenient parser and
    neither is on the allow-list, so accepting either would let through a
    request the UI could never produce.
    """
    count, rejection = validate_count(raw, allowed=PAGE_SIZES, default=10)

    assert count == 10
    assert rejection is not None
    assert rejection.parameter == "count"
    assert rejection.value == raw


def test_a_rejected_count_names_what_is_accepted():
    """The allow-list is discoverable at runtime rather than published."""
    _, rejection = validate_count("7", allowed=PAGE_SIZES, default=10)

    assert rejection.accepted == "10, 20, 50"


def test_the_allow_list_is_whatever_it_is_configured_to_be():
    """Not hardcoded to 10/20/50 — the list is deployment configuration."""
    count, rejection = validate_count("25", allowed=(25, 75), default=25)

    assert count == 25
    assert rejection is None


# --- total_pages ---------------------------------------------------------


@pytest.mark.parametrize(
    "catalogue,count,expected",
    [
        (100, 10, 10),
        (100, 20, 5),
        (100, 50, 2),
        (95, 10, 10),  # a short final page still counts
        (101, 10, 11),
        (1, 10, 1),
    ],
)
def test_total_pages_rounds_up_for_a_short_final_page(catalogue, count, expected):
    assert total_pages(catalogue, count) == expected


def test_an_empty_catalogue_still_has_one_page():
    """Returning 0 would make every page number invalid, including the default."""
    assert total_pages(0, 10) == 1


def test_a_nonsensical_count_does_not_divide_by_zero():
    """Defensive: validation should have rejected it, but this must not raise."""
    assert total_pages(100, 0) == 1


# --- page ----------------------------------------------------------------


def test_an_absent_page_is_page_one_without_complaint():
    """Not supplying a parameter is the default working as intended."""
    page, rejection = validate_page(None, last_page=10)

    assert page == 1
    assert rejection is None


@pytest.mark.parametrize("raw", ["", "   "])
def test_a_supplied_but_empty_page_is_a_rejection_not_an_absence(raw):
    """`?page=` is a parameter the user gave with an unusable value.

    Distinct from omitting it: the user expressed an intent the application
    cannot honour, so it is corrected and explained like any other bad value.
    Treating the two alike leaves `?page=` sitting in the address bar with no
    notice, which the Gherkin asserts against directly.
    """
    page, rejection = validate_page(raw, last_page=10)

    assert page == 1
    assert rejection is not None
    assert rejection.parameter == "page"


@pytest.mark.parametrize("raw,expected", [("1", 1), ("2", 2), ("10", 10)])
def test_a_page_inside_the_catalogue_is_accepted(raw, expected):
    page, rejection = validate_page(raw, last_page=10)

    assert page == expected
    assert rejection is None


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "11", "999", "1.5", "٣"])
def test_a_page_outside_the_catalogue_recovers_to_page_one(raw):
    """Every invalid form recovers identically — brief line 48.

    The Arabic-Indic digit is deliberate: `int()` accepts it, so a naive
    implementation would silently accept a page number nothing in the UI can
    produce and no other part of the system would round-trip.
    """
    page, rejection = validate_page(raw, last_page=10)

    assert page == 1
    assert rejection is not None
    assert rejection.parameter == "page"


def test_a_rejected_page_names_the_real_bound():
    _, rejection = validate_page("999", last_page=10)

    assert rejection.accepted == "1 to 10"


def test_the_notice_token_is_a_token_not_a_sentence():
    """Wording belongs to the UI; the URL carries an identifier."""
    _, rejection = validate_page("abc", last_page=10)

    assert rejection.notice == "invalid_page"


# --- grayscale -----------------------------------------------------------


def test_grayscale_is_off_when_not_asked_for():
    """F3.3's default. A checkbox that is not ticked sends nothing at all."""
    on, rejection = validate_grayscale(None)

    assert on is False
    assert rejection is None


@pytest.mark.parametrize("raw", ["1", "true", "on", "yes", "TRUE"])
def test_grayscale_accepts_the_forms_a_url_or_a_form_can_produce(raw):
    """A checkbox posts `on`; a hand-written URL is likelier to say `1` or
    `true`. All are the same intent, so all are honoured."""
    on, rejection = validate_grayscale(raw)

    assert on is True
    assert rejection is None


@pytest.mark.parametrize("raw", ["0", "false", "off", "no"])
def test_grayscale_can_be_turned_off_explicitly(raw):
    on, rejection = validate_grayscale(raw)

    assert on is False
    assert rejection is None


@pytest.mark.parametrize("raw", ["maybe", "2", "grey"])
def test_an_uninterpretable_grayscale_falls_back_and_is_reported(raw):
    on, rejection = validate_grayscale(raw)

    assert on is False
    assert rejection is not None
    assert rejection.parameter == "grayscale"


# --- blur ----------------------------------------------------------------


def test_blur_is_zero_when_not_asked_for():
    blur, rejection = validate_blur(None, maximum=10)

    assert blur == 0
    assert rejection is None


@pytest.mark.parametrize("raw,expected", [("0", 0), ("5", 5), ("10", 10)])
def test_blur_accepts_the_ends_and_middle_of_its_range(raw, expected):
    """F3.4 — 0 to 10, and the ends are inside the range, not outside it."""
    blur, rejection = validate_blur(raw, maximum=10)

    assert blur == expected
    assert rejection is None


@pytest.mark.parametrize("raw", ["11", "-1", "100", "abc", "3.5", ""])
def test_a_blur_outside_the_range_falls_back_to_none_and_is_reported(raw):
    """The range is fixed by the contract rather than by configuration, so
    unlike `size` this bound is part of the published interface."""
    blur, rejection = validate_blur(raw, maximum=10)

    assert blur == 0
    assert rejection is not None
    assert rejection.parameter == "blur"


def test_a_rejected_blur_names_its_range():
    _, rejection = validate_blur("11", maximum=10)

    assert "0" in rejection.accepted and "10" in rejection.accepted


# --- the two together ----------------------------------------------------


def test_count_is_resolved_before_page_so_the_bound_is_right():
    """`?count=50&page=2` is valid; at the default count page 2 of 2 exists.

    Validating page first would judge it against a 10-page bound computed from
    the wrong count. This is the ordering bug the implementation exists to
    avoid, and it only shows up when both parameters are supplied.
    """
    result = validate(
        {"count": "50", "page": "2"},
        page_sizes=PAGE_SIZES,
        default_count=10,
        catalogue_size=100,
    )

    assert result.count == 50
    assert result.page == 2
    assert result.is_valid


def test_a_page_valid_only_at_the_default_count_is_rejected_at_a_larger_one():
    """At count=50 a 100-image catalogue has 2 pages, so page 5 is out."""
    result = validate(
        {"count": "50", "page": "5"},
        page_sizes=PAGE_SIZES,
        default_count=10,
        catalogue_size=100,
    )

    assert result.page == 1
    assert [r.parameter for r in result.rejections] == ["page"]


def test_one_bad_parameter_does_not_discard_the_good_one():
    """ADR 6's central promise, at the validation layer."""
    result = validate(
        {"count": "7", "page": "3"},
        page_sizes=PAGE_SIZES,
        default_count=10,
        catalogue_size=100,
    )

    assert result.count == 10
    assert result.page == 3, "a valid page must survive an invalid count"
    assert [r.parameter for r in result.rejections] == ["count"]


def test_both_parameters_can_be_rejected_at_once():
    """The notice is a list because this case exists."""
    result = validate(
        {"count": "7", "page": "abc"},
        page_sizes=PAGE_SIZES,
        default_count=10,
        catalogue_size=100,
    )

    assert not result.is_valid
    assert {r.parameter for r in result.rejections} == {"count", "page"}


def test_nothing_supplied_is_valid():
    result = validate({}, page_sizes=PAGE_SIZES, default_count=10, catalogue_size=100)

    assert result.is_valid
    assert (result.page, result.count) == (1, 10)


def test_validate_resolves_every_parameter_the_gallery_understands():
    """One call, five parameters — the shell view and the image views both need
    the whole set, and validating them piecemeal is how two callers end up
    disagreeing about what a request meant."""
    result = validate(
        {"page": "2", "count": "20", "size": "large", "grayscale": "1", "blur": "5"},
        page_sizes=PAGE_SIZES,
        default_count=10,
        catalogue_size=100,
        default_size="medium",
        minimum_dimension=16,
        maximum_dimension=1600,
        maximum_blur=10,
    )

    assert result.is_valid
    assert (result.page, result.count) == (2, 20)
    assert (result.size, result.grayscale, result.blur) == ("large", True, 5)


def test_a_valid_filter_survives_an_invalid_one():
    """F3.6's central promise, and a scenario asserts it directly: one bad
    parameter must not discard the good ones alongside it."""
    result = validate(
        {"size": "enormous", "blur": "6"},
        page_sizes=PAGE_SIZES,
        default_count=10,
        catalogue_size=100,
        default_size="medium",
        minimum_dimension=16,
        maximum_dimension=1600,
        maximum_blur=10,
    )

    assert result.size == "medium", "the bad size falls back"
    assert result.blur == 6, "the good blur survives"
    assert [r.parameter for r in result.rejections] == ["size"]


def test_a_rejection_serialises_to_the_documented_error_shape():
    """docs/api-contract.md's `errors` array carries these three fields."""
    result = validate(
        {"count": "7"}, page_sizes=PAGE_SIZES, default_count=10, catalogue_size=100
    )

    assert result.rejections[0].as_dict() == {
        "parameter": "count",
        "value": "7",
        "accepted": "10, 20, 50",
    }
