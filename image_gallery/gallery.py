"""Which images belong on a page.

The orchestrator of docs/adr/0013-module-structure.md — the only module that
knows a page is composed of many images. It knows nothing about where the bytes
come from, which keeps pagination on this side of the provider boundary and the
provider swappable.

Ids are derivable rather than stored (docs/adr/0004-bounded-catalogue.md), so a
page is arithmetic over the catalogue bound. The browser performs the same
arithmetic to build its tiles
(docs/adr/0020-ids-are-derived-in-the-browser.md); this side of it is what
validation uses to decide whether a requested page exists at all.
"""

from __future__ import annotations


def image_ids(page: int, count: int, catalogue_size: int) -> range:
    """The ids on a page, bounded by the catalogue.

    The range is clamped at the catalogue's end, so the last page carries
    however many images remain rather than running past the bound. A page
    beyond the end yields an empty range — the caller is expected to have
    rejected it during validation, but arithmetic that quietly wrapped would
    hide that failure rather than surface it.
    """
    first = (page - 1) * count + 1
    last = min(first + count - 1, catalogue_size)
    if first > catalogue_size:
        return range(0)
    return range(first, last + 1)
