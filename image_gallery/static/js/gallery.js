/*
 * The gallery client.
 *
 * Builds the grid from the bounds the shell published, deriving the id range
 * for the current page rather than fetching it
 * (docs/adr/0020-ids-are-derived-in-the-browser.md). There is no metadata call:
 * page loading is one document request, then one image request per tile.
 *
 * Stage 1 stops at the placeholders. Stage 2 gives each tile an <img> pointing
 * at this application's `image` endpoint — the browser never contacts the image
 * provider directly (docs/adr/0003-django-as-image-proxy.md), and the id a tile
 * carries is what the server reads as the provider's seed
 * (docs/adr/0009-url-vocabularies.md).
 *
 * The bounds are read from the document, never assumed: catalogue size and page
 * size are deployment configuration, and a default hardcoded here would be a
 * second place that could disagree with settings.py.
 */

(function () {
  "use strict";

  var grid = document.getElementById("gallery");
  if (!grid) return;

  function readBound(name) {
    var value = Number(grid.dataset[name]);
    return Number.isFinite(value) && value > 0 ? value : null;
  }

  /* The same arithmetic the server uses to validate a page number
   * (image_gallery/gallery.py). The two must agree: this side decides what to
   * render, that side decides what is in range, and a divergence would show as
   * tiles requesting ids the server rejects.
   *
   * Clamped at the catalogue's end so a short final page carries what remains
   * rather than running past the bound. */
  function imageIds(page, count, catalogueSize) {
    var first = (page - 1) * count + 1;
    if (first > catalogueSize) return [];

    var last = Math.min(first + count - 1, catalogueSize);
    var ids = [];
    for (var id = first; id <= last; id++) ids.push(id);
    return ids;
  }

  /* A tile is a placeholder frame that an image later fades into. The frame
   * holds its aspect ratio from the moment it is created (app.css
   * `.tile__frame`), so the grid reserves its full layout before any image has
   * loaded and never reflows as they arrive. */
  function buildTile(id) {
    var tile = document.createElement("li");
    tile.className = "tile";
    tile.dataset.testid = "image-tile";
    tile.dataset.imageId = String(id);
    tile.dataset.state = "pending";

    var frame = document.createElement("span");
    frame.className = "tile__frame";
    tile.appendChild(frame);

    return tile;
  }

  /* Created on demand rather than revealed: "no validation message is shown"
   * asserts the element is absent, so an always-present empty banner would
   * fail it. Inserted before the grid, which renders normally beneath — the
   * notice is informational, not an error page
   * (docs/adr/0006-recover-and-explain.md). */
  function showNotice(message) {
    var banner = document.createElement("p");
    banner.className = "notice";
    banner.dataset.testid = "notice";
    banner.setAttribute("role", "status");
    banner.textContent = message;

    grid.parentNode.insertBefore(banner, grid);
  }

  /* The wording lives here rather than in the URL: `?notice=` carries a token
   * so the address stays short and the phrasing stays a UI concern
   * (docs/adr/0006-recover-and-explain.md). Several parameters can be invalid
   * at once, so the key repeats and every message is shown. */
  var NOTICES = {
    invalid_page: "That page doesn't exist — showing page 1.",
    invalid_count: "That image count isn't available — showing 10 per page.",
  };

  function showNotices() {
    var tokens = new URLSearchParams(window.location.search).getAll("notice");
    var messages = tokens
      .map(function (token) {
        return NOTICES[token];
      })
      .filter(Boolean);

    if (messages.length) showNotice(messages.join(" "));
  }

  function render() {
    var page = readBound("page");
    var count = readBound("count");
    var catalogueSize = readBound("catalogueSize");

    /* Absent or unusable bounds mean the shell did not render what this script
     * requires. Failing visibly beats rendering an empty grid that looks like
     * an empty catalogue. */
    if (page === null || count === null || catalogueSize === null) {
      showNotice("The gallery could not be loaded.");
      return;
    }

    var fragment = document.createDocumentFragment();
    imageIds(page, count, catalogueSize).forEach(function (id) {
      fragment.appendChild(buildTile(id));
    });

    grid.replaceChildren(fragment);
    grid.setAttribute("aria-busy", "false");
  }

  showNotices();
  render();
})();
