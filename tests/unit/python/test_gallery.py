"""Page composition: which ids belong on a page.

The server no longer serves this range to the browser — the client derives it
(docs/adr/0020-ids-are-derived-in-the-browser.md). It is still computed here,
because validating a page number means knowing where the catalogue ends, and
because two implementations of one rule have to agree.

**That agreement is what these tests protect.** `tests/unit/js/derive.test.js`
asserts the same ranges against the JavaScript, case for case. If the two ever
diverge, tiles will request ids the server considers out of range.
"""

import pytest

from image_gallery.gallery import image_ids


def ids(page, count=10, catalogue_size=100):
    return list(image_ids(page, count, catalogue_size))


def test_page_one_holds_the_first_ten_images():
    assert ids(1) == list(range(1, 11))


def test_page_two_continues_where_page_one_ended():
    """The off-by-one this arithmetic exists to get right (F2.6)."""
    assert ids(2) == list(range(11, 21))


def test_the_last_page_ends_at_the_catalogue_bound():
    assert ids(10) == list(range(91, 101))


def test_pages_do_not_overlap_and_leave_no_gaps():
    """Every image appears exactly once across the whole catalogue.

    Stronger than checking a page or two: it catches a fencepost error that
    happens to be correct at the boundaries tested above.
    """
    seen = [image_id for page in range(1, 11) for image_id in ids(page)]

    assert seen == list(range(1, 101))


def test_a_short_final_page_is_not_padded():
    """A 95-image catalogue ends with five images, not ten."""
    assert ids(10, catalogue_size=95) == [91, 92, 93, 94, 95]


def test_an_uneven_catalogue_is_still_covered_exactly_once():
    """Mirrors the JS test of the same name — the awkward divisor case."""
    seen = [image_id for page in range(1, 11) for image_id in ids(page, catalogue_size=95)]

    assert seen == list(range(1, 96))


def test_a_page_past_the_end_is_empty_rather_than_wrapping():
    """Validation should have rejected this, so it must not quietly succeed."""
    assert ids(11) == []


@pytest.mark.parametrize(
    "page,count,expected_first,expected_len",
    [(1, 20, 1, 20), (2, 20, 21, 20), (2, 50, 51, 50), (1, 50, 1, 50)],
)
def test_ranges_follow_the_chosen_count(page, count, expected_first, expected_len):
    got = ids(page, count=count)

    assert got[0] == expected_first
    assert len(got) == expected_len


def test_an_empty_catalogue_yields_no_images():
    """No tiles rather than a crash: the shell still renders its shape."""
    assert ids(1, catalogue_size=0) == []
