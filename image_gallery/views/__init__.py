"""Views, one class per module (docs/adr/0013-module-structure.md).

Re-exported here so `urls.py` reads as it did when this was a single module,
and so the URLconf need not know which file a view lives in.

`mixins.py` is deliberately absent. ADR 13 introduces it to hold the parameter
parsing that the API views share, and only `ImageProxyView` parses parameters
so far — the metadata endpoint was removed in
docs/adr/0020-ids-are-derived-in-the-browser.md. It arrives with `ImageAPIView`
in stage 9, which genuinely does share that prologue. A mixin with one user
would be indirection without abstraction.
"""

from .detail import ImageDetailView
from .health import HealthView
from .image import ImageProxyView
from .shell import AppShellView

__all__ = ["AppShellView", "HealthView", "ImageDetailView", "ImageProxyView"]
