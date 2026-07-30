"""Views, one class per module (docs/adr/0013-module-structure.md).

Re-exported here so `urls.py` reads as it did when this was a single module,
and so the URLconf need not know which file a view lives in.

`mixins.py` is still deliberately absent. ADR 13 introduces it to hold the
parameter parsing the API views share, and `ImageApiView` has now arrived — but
the two do different things with the query string. `ImageProxyView` **refuses**
a bad parameter with a 400, because an `<img>` asking for something impossible
is a client bug; `ImageApiView` **recovers** and explains, because a person
pasted the URL. Sharing the prologue would mean parameterising the part that
differs, which is the whole of it.
"""

from .api_image import ImageApiView
from .detail import ImageDetailView
from .health import HealthView
from .image import ImageProxyView
from .shell import AppShellView

__all__ = [
    "AppShellView",
    "HealthView",
    "ImageApiView",
    "ImageDetailView",
    "ImageProxyView",
]
