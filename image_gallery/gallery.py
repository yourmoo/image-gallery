"""Which images belong on a page.

The orchestrator of docs/adr/0013-module-structure.md — the only module that
knows a page is composed of many images. It knows nothing about where the bytes
come from, which keeps pagination on this side of the provider boundary and the
provider swappable.

Ids are derivable rather than stored (docs/adr/0004-bounded-catalogue.md), so a
page is arithmetic over the catalogue bound. The browser performs the same
arithmetic to build its tiles, in `static/js/derive.js`
(docs/adr/0020-ids-are-derived-in-the-browser.md); this side of it is what
validation uses to decide whether a requested page exists at all. The two are
tested against the same cases, in `tests/unit/python/` and `tests/unit/js/`.
"""

from __future__ import annotations


def image_ids(page: int, count: int, catalogue_size: int) -> range:
    """The ids on a page, clamped at the catalogue's end.

    The last page carries however many images remain rather than being padded.
    A page beyond the end yields an empty range — the caller is expected to
    have rejected it during validation, but arithmetic that quietly wrapped
    would hide that failure rather than surface it.
    """
    first = (page - 1) * count + 1
    if first > catalogue_size:
        return range(0)

    last = min(first + count - 1, catalogue_size)
    return range(first, last + 1)
