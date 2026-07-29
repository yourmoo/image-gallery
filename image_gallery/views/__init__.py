"""Views, one class per module (docs/adr/0013-module-structure.md).

Re-exported here so `urls.py` reads as it did when this was a single module,
and so the URLconf need not know which file a view lives in.

`mixins.py` is deliberately absent. ADR 13 introduces it to hold the parameter
parsing that the API views share, and there are no API views yet — the metadata
endpoint was removed in docs/adr/0020-ids-are-derived-in-the-browser.md. It
arrives with `ImageAPIView` and `ImageProxyView`, which genuinely do share a
prologue. A mixin with one user would be indirection without abstraction.
"""

from .health import HealthView
from .shell import AppShellView

__all__ = ["AppShellView", "HealthView"]
