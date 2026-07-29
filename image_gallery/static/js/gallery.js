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

  /* The proxy answers 504 when it has nothing to show, so `error` fires for a
   * tile that genuinely could not be filled. A failed tile must not look like
   * one that is still loading (docs/ui/design-system.md), so the <img> is
   * removed and the frame takes the warm failed treatment.
   *
   * Counted as it happens rather than tallied at the end: images arrive
   * independently and there is no moment when "all of them are done". */
  img.addEventListener("error", () => {
    tile.dataset.state = "failed";
    tile.classList.add("tile--failed");
    img.remove();
    frame.dataset.testid = "image-failed";
    noteDegraded();
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

/* The degraded banner, assembled client-side.
 *
 * Which images failed is not known when the document is served — the fetches
 * happen afterwards, one per tile (docs/adr/0017-image-fetch-timing.md) — so
 * the count is kept here and the banner appears on the first failure.
 *
 * Warm rather than cool: this reports what the *system* did when upstream was
 * unavailable, where the validation notice reports what *you* asked for and
 * fell back from. The design system gives them different palettes for exactly
 * that reason, so they must not share an element.
 */
let degradedCount = 0;

function noteDegraded() {
  degradedCount += 1;

  /* Carries `data-testid="notice"` because that is the hook the suite binds
   * to for both banners. Safe because they never co-occur: the only scenario
   * asserting no notice is present is one where nothing failed. The modifier
   * class is what makes this one warm rather than cool. */
  let banner = document.querySelector('[data-testid="notice"].notice--warn');
  if (!banner) {
    banner = document.createElement("p");
    banner.className = "notice notice--warn";
    banner.dataset.testid = "notice";
    banner.setAttribute("role", "status");
    grid.parentNode.insertBefore(banner, grid);
  }

  banner.textContent =
    degradedCount === 1
      ? "One image could not be loaded."
      : `${degradedCount} images could not be loaded.`;
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

/* Controls apply instantly — no Apply button, which is the ordinary CSR
 * expectation and removes a click from every change (docs/ui/ui-notes.md).
 *
 * Changing the count returns to page 1 deliberately: at 50 per page there is
 * no page 7, so keeping the number would land the user on a page that no
 * longer exists and trigger a correction they did not ask for.
 *
 * A full navigation rather than a re-render in place. The server validates the
 * new value, the address bar stays truthful, and the result is bookmarkable —
 * all of which a client-side re-render would have to reimplement.
 */
function wireControls() {
  const count = document.querySelector('[data-testid="count-control"]');
  if (!count) return;

  count.addEventListener("change", () => {
    const params = new URLSearchParams(window.location.search);
    params.set("count", count.value);
    params.delete("page");
    params.delete("notice");
    window.location.search = params.toString();
  });
}

if (grid) {
  const tokens = new URLSearchParams(window.location.search).getAll("notice");
  for (const message of noticeMessages(tokens)) showNotice(message);

  render();
  wireControls();
}
