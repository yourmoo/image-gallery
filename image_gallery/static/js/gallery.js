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

import {
  imageIds,
  imageUrl,
  noticeMessages,
  pageUrl,
  pagination,
  readBounds,
  totalPages,
} from "./derive.js";

const grid = document.getElementById("gallery");

/* Markup follows docs/ui/design-system.md § Image grid. The frame holds its
 * aspect ratio from the moment it is created, so the grid reserves its full
 * layout before any image loads and never reflows as they arrive.
 *
 * Each <img> is a separate request to this application's image endpoint, which
 * is what makes the page composed of one upstream call per tile (F2.7) and
 * what the per-tile placeholder exists for: at 50 images the page is roughly
 * 1 MB, arriving progressively.
 */
function buildTile(id, template, variations) {
  const tile = document.createElement("li");
  tile.className = "tile";
  tile.dataset.testid = "image-tile";
  tile.dataset.imageId = String(id);
  tile.dataset.state = "pending";

  const frame = document.createElement("span");
  frame.className = "tile__frame";

  const img = document.createElement("img");
  img.className = "tile__image";
  img.dataset.testid = "image-figure";
  img.dataset.loaded = "false";
  img.alt = `Image ${id}`;
  /* Below the fold this defers the request entirely, which matters at 50 per
   * page. The tile keeps its reserved space either way. */
  img.loading = "lazy";
  img.src = imageUrl(template, id, variations);

  /* `load` fires for the placeholder GIF too — a degraded tile is still a
   * decoded image — so "loaded" here means "the browser has something to
   * paint", and the degraded banner is driven by the server's own count
   * rather than by this event. */
  img.addEventListener("load", () => {
    img.dataset.loaded = "true";
    tile.dataset.state = "loaded";
  });

  /* Only a genuine transport failure reaches here, since the proxy answers 200
   * with a placeholder when upstream is down. A failed tile must not look like
   * one that is still loading (docs/ui/design-system.md). */
  img.addEventListener("error", () => {
    tile.dataset.state = "failed";
    tile.classList.add("tile--failed");
    img.remove();
    frame.dataset.testid = "image-failed";
  });

  frame.appendChild(img);
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

/* Real <a href> elements rather than buttons, so middle-click and copy-link
 * keep working (docs/ui/design-system.md § Pagination). Every link carries the
 * active variations, which is F2.3.
 *
 * An end renders no element at all — the Gherkin asserts absence, not a
 * disabled state, so there is nothing here to disable. */
function buildPagination(page, pages, currentParams) {
  const nav = document.createElement("nav");
  nav.className = "pagination";
  nav.dataset.testid = "pagination";
  nav.setAttribute("aria-label", "Pagination");

  const links = pagination(page, pages);

  if (links.previous !== null) {
    nav.appendChild(
      buildPageLink(links.previous, currentParams, "Previous", "prev-page")
    );
  }

  const status = document.createElement("span");
  status.className = "pagination__status";
  status.dataset.testid = "page-status";
  status.textContent = links.status;
  nav.appendChild(status);

  if (links.next !== null) {
    nav.appendChild(buildPageLink(links.next, currentParams, "Next", "next-page"));
  }

  return nav;
}

function buildPageLink(page, currentParams, label, testid) {
  const link = document.createElement("a");
  link.className = "pagination__link";
  link.dataset.testid = testid;
  link.href = pageUrl(page, currentParams);
  link.textContent = label;
  return link;
}

function render() {
  const bounds = readBounds(grid.dataset);
  const template = grid.dataset.imageUrlTemplate;

  /* Unusable bounds, or no URL template, mean the shell did not render what
   * this script requires. Failing visibly beats an empty grid, which would
   * look like an empty catalogue rather than a broken page. */
  if (bounds === null || !template) {
    showNotice("The gallery could not be loaded.");
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const id of imageIds(bounds.page, bounds.count, bounds.catalogueSize)) {
    fragment.appendChild(buildTile(id, template, {}));
  }

  grid.replaceChildren(fragment);
  grid.dataset.state = "ready";

  const params = new URLSearchParams(window.location.search);
  const pages = totalPages(bounds.catalogueSize, bounds.count);
  grid.parentNode.insertBefore(buildPagination(bounds.page, pages, params), grid.nextSibling);
}

if (grid) {
  const tokens = new URLSearchParams(window.location.search).getAll("notice");
  for (const message of noticeMessages(tokens)) showNotice(message);

  render();
}
