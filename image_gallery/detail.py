"""The one rule the detail view adds: which size it renders at.

docs/adr/0007-detail-view-size.md resolves an apparent conflict in the brief.
Line 71 asks the detail view to display a *larger* version; line 72 asks it to
reflect *all active transformations*. Taken together they contradict each other
whenever the gallery is showing `small`.

The resolution is by category rather than precedence. **Size is presentation** —
a grid wants small images so many fit, a detail page wants a big one because it
shows only one. **Grayscale and blur are content** — they describe how the image
should look anywhere. Read that way "all active transformations" means the
filters, and "larger" governs size; neither requirement overrides the other.

So this module answers exactly one question, and the filters are not its
business: they carry over untouched.

Pure, so it is testable without Django, and separate from `views/` because it
is a rule rather than an HTTP concern.
"""

from __future__ import annotations


def _dimensions(size: str) -> tuple[int, int] | None:
    """Pixels for a `WxH` size, or None for a named one.

    Named sizes are not resolved here — that is provider vocabulary
    (docs/adr/0013-module-structure.md). This module only needs to compare a
    *custom* size against the configured `large`, and a name is by definition
    not larger than itself.
    """
    width, separator, height = str(size).lower().partition("x")
    if not separator:
        return None
    try:
        return int(width), int(height)
    except ValueError:
        return None


def detail_size(gallery_size: str, *, large: str) -> str:
    """The size the detail view should render at.

    "Never smaller than the gallery, and never smaller than `large`."

    A named size always becomes `large`, so "larger" is satisfied
    unconditionally rather than in most cases. A custom size is kept only when
    it exceeds `large` in either dimension: browsing at `1200x900` and opening
    an image must not drop to 800x800, which would make the detail view
    *smaller* than the grid — the precise opposite of what the requirement
    asks.

    A custom size that happens to equal `large` is returned as the name, since
    the pixels are identical and the name is what the parameters panel shows.
    """
    requested = _dimensions(gallery_size)
    if requested is None:
        return "large"

    ceiling = _dimensions(large)
    if ceiling is None:
        return "large"

    width, height = requested
    if width > ceiling[0] or height > ceiling[1]:
        return gallery_size.lower()

    return "large"
