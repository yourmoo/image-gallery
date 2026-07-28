// main.js — wiring: events, fetch lifecycle, history.
// Controls apply instantly; there is no Apply button (design-system.md §4).

import { read, write, correct, DEFAULTS } from "./state.js";
import { fetchImages, Unreachable } from "./api.js";
import * as ui from "./render.js";

const BLUR_DEBOUNCE = 180; // one request per drag, not eleven

const dom = {
  notice: document.querySelector("[data-slot='notice']"),
  banner: document.querySelector("[data-slot='banner']"),
  controls: document.querySelector(".controls"),
  loading: document.querySelector(".loading"),
  gallery: document.querySelector(".gallery"),
  pagination: document.querySelector(".pagination"),
  results: document.querySelector("[data-slot='results']"),
};

let state = DEFAULTS;

async function load({ push = false, notices = [] } = {}) {
  if (push) write(state);
  ui.syncControls(dom.controls, state);
  ui.setLoading(dom.loading, dom.gallery, true);

  try {
    const data = await fetchImages(state);

    // Invalid page under CSR is a clamp + replaceState, not a redirect:
    // Back must not return to the bad page.
    if (data.page !== state.page) {
      state = { ...state, page: data.page };
      correct(state);
      notices = [...notices, "That page doesn't exist — showing page 1."];
      ui.syncControls(dom.controls, state);
    }

    ui.renderNotice(dom.notice, [...notices, ...(data.notices || [])]);
    ui.renderDegraded(dom.banner, data.degraded ? data.cached_at : null);

    if (!data.images.length) {
      dom.gallery.replaceChildren();
      ui.renderEmpty(dom.results, {
        testid: "empty",
        title: "No images to show",
        body: "This page is beyond the end of the gallery.",
        action: { href: "?page=1", label: "Back to page 1" },
      });
      dom.pagination.replaceChildren();
      return;
    }

    dom.results.replaceChildren();
    ui.renderGallery(dom.gallery, state, data.images);
    ui.renderPagination(dom.pagination, state, {
      page: data.page,
      totalPages: data.total_pages,
    });
  } catch (err) {
    if (err.name === "AbortError") return; // superseded by a newer request
    dom.gallery.replaceChildren();
    dom.pagination.replaceChildren();
    ui.renderEmpty(dom.results, {
      testid: "unreachable",
      title: err instanceof Unreachable
        ? "The image service is unreachable"
        : "Something went wrong",
      body: "Nothing cached to fall back to yet. Your filters are kept in the URL.",
      action: { href: location.href, label: "Try again" },
    });
  } finally {
    ui.setLoading(dom.loading, dom.gallery, false);
  }
}

function apply(patch, { resetPage = true } = {}) {
  state = { ...state, ...patch, ...(resetPage ? { page: 1 } : {}) };
  load({ push: true });
}

/* ---------- events ---------- */

// select + checkbox: one change, one fetch.
dom.controls.addEventListener("change", (e) => {
  const { name, value, checked } = e.target;
  if (name === "size") apply({ size: value });
  else if (name === "count") apply({ count: Number(value) });
  else if (name === "grayscale") apply({ grayscale: checked });
});

// The blur range is why an Apply button was tempting. Instead: paint the
// readout on every input (free), debounce the request, abort the last one.
let blurTimer;
dom.controls.addEventListener("input", (e) => {
  if (e.target.name !== "blur") return;
  const value = Number(e.target.value);
  dom.controls.querySelector('output[for="blur"]').textContent = value;
  clearTimeout(blurTimer);
  blurTimer = setTimeout(() => apply({ blur: value }), BLUR_DEBOUNCE);
});

// Chips reset one parameter each.
dom.controls.addEventListener("click", (e) => {
  const key = e.target.dataset.reset;
  if (key) apply({ [key]: DEFAULTS[key] });
});

// Real <a href> links, intercepted — middle-click and copy-link still work.
dom.pagination.addEventListener("click", (e) => {
  const link = e.target.closest(".pagination__link");
  if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  apply({ page: Number(link.dataset.page) }, { resetPage: false });
});

// Back and forward are a re-render, never a fetch-and-push.
addEventListener("popstate", () => {
  const { state: next, notices } = read();
  state = next;
  load({ notices });
});

/* ---------- boot ---------- */

const initial = read();
state = initial.state;
load({ notices: initial.notices });
