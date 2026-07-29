"""Validation is pure, so these tests need no Django and no request.

The rules here are the ones both entry points share — the shell view's redirect
and the API's 400 — so a gap in this file is a gap in both
(docs/adr/0019-validation-errors-carry-a-usable-payload.md).
"""

import pytest

from image_gallery.validation import (
    total_pages,
    validate,
    validate_count,
    validate_page,
)

PAGE_SIZES = (10, 20, 50)


# --- count ---------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_absent_count_takes_the_default_without_complaint(raw):
    """An unsupplied parameter is the default working as intended.

    Reporting it would put a notice on every first visit to the gallery.
    """
    count, rejection = validate_count(raw, allowed=PAGE_SIZES, default=10)

    assert count == 10
    assert rejection is None


@pytest.mark.parametrize("raw,expected", [("10", 10), ("20", 20), ("50", 50)])
def test_allow_listed_counts_are_accepted(raw, expected):
    count, rejection = validate_count(raw, allowed=PAGE_SIZES, default=10)

    assert count == expected
    assert rejection is None


@pytest.mark.parametrize("raw", ["7", "0", "-10", "abc", "10.5", "1e1"])
def test_a_count_outside_the_allow_list_falls_back_and_is_reported(raw):
    """Includes forms that parse as numbers but are not offered.

    `10.5` and `1e1` matter: both are meaningful to a lenient parser and
    neither is on the allow-list, so accepting either would let a request
    through that the UI could never produce.
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


# --- page ----------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_absent_page_is_page_one_without_complaint(raw):
    page, rejection = validate_page(raw, last_page=10)

    assert page == 1
    assert rejection is None


@pytest.mark.parametrize("raw,expected", [("1", 1), ("2", 2), ("10", 10)])
def test_a_page_inside_the_catalogue_is_accepted(raw, expected):
    page, rejection = validate_page(raw, last_page=10)

    assert page == expected
    assert rejection is None


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "11", "999", "1.5"])
def test_a_page_outside_the_catalogue_recovers_to_page_one(raw):
    """Every invalid form recovers identically — brief line 48."""
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
    result = validate(
        {}, page_sizes=PAGE_SIZES, default_count=10, catalogue_size=100
    )

    assert result.is_valid
    assert (result.page, result.count) == (1, 10)
