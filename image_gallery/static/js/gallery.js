/*
 * The gallery client: DOM wiring only.
 *
 * Every decision this file makes is delegated to derive.js, which is pure and
 * unit-tested (tests/unit/js/derive.test.js). What is left here is construction and
 * insertion — the parts that need a document and are covered by the browser
 * tier instead.
 *
 * The grid is built from bounds the shell published rather than fetched: there
 * is no metadata call (docs/adr/0020-ids-are-derived-in-the-browser.md).
 * Loading a page is one document request, then one image request per tile.
 *
 * Stage 1 stops at the placeholders. Stage 2 gives each tile an <img> pointing
 * at this application's `image` endpoint — the browser never contacts the
 * provider directly (docs/adr/0003-django-as-image-proxy.md), and the id a tile
 * carries is what the server reads as the provider's seed
 * (docs/adr/0009-url-vocabularies.md).
 */

import { imageIds, noticeMessages, readBounds } from "./derive.js";

const grid = document.getElementById("gallery");

/* Markup follows docs/ui/design-system.md § Image grid. The frame holds its
 * aspect ratio from the moment it is created, so the grid reserves its full
 * layout before any image loads and never reflows as they arrive. */
function buildTile(id) {
  const tile = document.createElement("li");
  tile.className = "tile";
  tile.dataset.testid = "image-tile";
  tile.dataset.imageId = String(id);
  tile.dataset.state = "pending";

  const frame = document.createElement("span");
  frame.className = "tile__frame";
  tile.appendChild(frame);

  return tile;
}

/* Created on demand rather than revealed: the scenario "no validation message
 * is shown" asserts the element is absent, so an always-present empty banner
 * would fail it. Inserted above the grid, which renders normally beneath — the
 * notice is informational, not an error page
 * (docs/adr/0006-recover-and-explain.md). */
function showNotice(message) {
  const banner = document.createElement("p");
  banner.className = "notice";
  banner.dataset.testid = "notice";
  banner.setAttribute("role", "status");
  banner.textContent = message;

  grid.parentNode.insertBefore(banner, grid);
}

function render() {
  const bounds = readBounds(grid.dataset);

  /* Unusable bounds mean the shell did not render what this script requires.
   * Failing visibly beats an empty grid, which would look like an empty
   * catalogue rather than a broken page. */
  if (bounds === null) {
    showNotice("The gallery could not be loaded.");
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const id of imageIds(bounds.page, bounds.count, bounds.catalogueSize)) {
    fragment.appendChild(buildTile(id));
  }

  grid.replaceChildren(fragment);
  grid.dataset.state = "ready";
}

if (grid) {
  const tokens = new URLSearchParams(window.location.search).getAll("notice");
  for (const message of noticeMessages(tokens)) showNotice(message);

  render();
}
