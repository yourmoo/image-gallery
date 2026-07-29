"""Views, one class per module (docs/adr/0013-module-structure.md).

Re-exported here so `urls.py` reads as it did when this was a single module,
and so the URLconf does not have to know which file a view lives in.

`mixins.py` is deliberately absent. It exists in ADR 13 to hold the parameter
parsing that the API views share, and there are no API views yet — the metadata
endpoint was removed in docs/adr/0020-ids-are-derived-in-the-browser.md. It
arrives with `ImageAPIView` and `ImageProxyView`, which do share a prologue.
"""

from .health import HealthView
from .shell import AppShellView

__all__ = ["AppShellView", "HealthView"]
