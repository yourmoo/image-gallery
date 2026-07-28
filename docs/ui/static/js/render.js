// render.js — state + data => DOM. Reads no globals, fires no fetches,
// so a failure state is just another render. See design-system.md §3.

import { DEFAULTS, toQuery, customCellFloor } from "./state.js";

const el = (tag, props = {}, children = []) => {
  const node = Object.assign(document.createElement(tag), props);
  for (const c of [].concat(children)) if (c) node.append(c);
  return node;
};

/* ---------- notice banner (F2.2, F3.6) ---------- */

// One banner, one list — several parameters can be invalid at once.
export function renderNotice(mount, messages) {
  mount.replaceChildren();
  if (!messages.length) return;

  const list = el("ul", { className: "notice__list" });
  for (const m of messages) list.append(el("li", { textContent: m }));

  const dismiss = el("button", {
    className: "notice__dismiss",
    type: "button",
    ariaLabel: "Dismiss",
    textContent: "\u00d7",
    onclick: () => mount.replaceChildren(),
  });

  mount.append(el("div", {
    className: "notice",
    role: "status",
    dataset: { testid: "notice" },
  }, [list, dismiss]));
}

/* ---------- controls ---------- */

// Rendered from state on every navigation, so which value is active is
// always visible on load — including after Back.
export function syncControls(root, state) {
  root.querySelector("#size").value = state.size;
  root.querySelector("#grayscale").checked = state.grayscale;
  root.querySelector("#blur").value = state.blur;
  root.querySelector("#count").value = state.count;
  root.querySelector('output[for="blur"]').textContent = state.blur;

  for (const [key, id] of [
    ["size", "#size"], ["grayscale", "#grayscale"],
    ["blur", "#blur"], ["count", "#count"],
  ]) {
    const control = root.querySelector(id).closest(".control");
    control.dataset.active = String(state[key] !== DEFAULTS[key]);
  }

  renderChips(root.querySelector(".chips"), state);
}

function renderChips(mount, state) {
  mount.replaceChildren();
  const active = [
    state.size !== DEFAULTS.size && ["size", `size ${state.size}`],
    state.grayscale && ["grayscale", "grayscale on"],
    state.blur !== DEFAULTS.blur && ["blur", `blur ${state.blur}`],
    state.count !== DEFAULTS.count && ["count", `${state.count} per page`],
  ].filter(Boolean);

  for (const [key, label] of active) {
    mount.append(el("li", { className: "chip" }, [
      label,
      el("button", {
        className: "chip__remove",
        type: "button",
        ariaLabel: `Remove ${label}`,
        textContent: "\u00d7",
        dataset: { reset: key },
      }),
    ]));
  }
}

/* ---------- gallery ---------- */

export function renderGallery(mount, state, images) {
  mount.dataset.size = customCellFloor(state.size) ? "custom" : state.size;
  const floor = customCellFloor(state.size);
  if (floor) mount.style.setProperty("--cell-custom", floor);

  mount.replaceChildren();
  for (const image of images) mount.append(tile(state, image));
}

function tile(state, image) {
  const caption = el("p", { className: "tile__caption", textContent: `#${image.id}` });

  // A failed tile must never look like a loading tile.
  if (image.failed) {
    return el("li", {
      className: "tile tile--failed",
      dataset: { testid: "tile-failed" },
    }, [
      el("span", { className: "tile__frame" }, [
        el("span", { className: "tile__fail" }, [
          el("span", { className: "tile__fail-dot", ariaHidden: "true" }),
          "Couldn't load",
          el("a", { className: "tile__retry", href: image.url, textContent: "Retry" }),
        ]),
      ]),
      caption,
    ]);
  }

  const img = el("img", {
    className: "tile__image",
    src: image.url,              // Django, never picsum
    alt: `Image ${image.id}`,
    width: image.width,          // reserve layout: the grid never reflows
    height: image.height,
    loading: "lazy",
  });
  img.dataset.loaded = "false";
  img.addEventListener("load", () => { img.dataset.loaded = "true"; }, { once: true });
  img.addEventListener("error", () => {
    img.closest(".tile").replaceWith(tile(state, { ...image, failed: true }));
  }, { once: true });

  return el("li", { className: "tile" }, [
    el("a", {
      className: "tile__link",
      href: `/images/${image.id}/${toQuery(state)}`,
    }, [el("span", { className: "tile__frame" }, [img])]),
    caption,
  ]);
}

/* ---------- loading ---------- */

// Two states that must not be conflated: the page fetch dims the grid it
// already has; each tile's own fetch is the placeholder inside it.
export function setLoading(indicator, gallery, loading) {
  indicator.hidden = !loading;
  gallery.dataset.state = loading ? "loading" : "ready";
}

/* ---------- pagination (F2.1, F2.3) ---------- */

// No element at the ends — the Gherkin asserts absence, not a disabled state.
export function renderPagination(mount, state, { page, totalPages }) {
  mount.replaceChildren();

  if (page > 1) {
    mount.append(el("a", {
      className: "pagination__link",
      href: toQuery({ ...state, page: page - 1 }),
      textContent: "Previous",
      dataset: { page: page - 1 },
    }));
  }

  mount.append(el("span", {
    className: "pagination__status",
    textContent: `Page ${page} of ${totalPages}`,
  }));

  if (page < totalPages) {
    mount.append(el("a", {
      className: "pagination__link",
      href: toQuery({ ...state, page: page + 1 }),
      textContent: "Next",
      dataset: { page: page + 1 },
    }));
  }
}

/* ---------- degraded / empty / unreachable ---------- */

export function renderDegraded(mount, cachedAt) {
  mount.replaceChildren();
  if (!cachedAt) return;
  mount.append(el("div", {
    className: "banner banner--warn",
    role: "status",
    dataset: { testid: "degraded" },
    textContent: `picsum.dev isn't responding — showing cached images from ${cachedAt}. Filters still apply.`,
  }));
}

export function renderEmpty(mount, { testid, title, body, action }) {
  mount.replaceChildren(el("div", { className: "empty", dataset: { testid } }, [
    el("p", { className: "empty__title", textContent: title }),
    el("p", { className: "empty__body", textContent: body }),
    el("a", { className: "button button--quiet", href: action.href, textContent: action.label }),
  ]));
}

/* ---------- detail (F4.4) ---------- */

// Reports what was actually used: size reads "large" even when the gallery
// was showing "small". The panel is where the user finds that out.
export function renderParams(mount, image) {
  mount.replaceChildren();
  const rows = [
    ["Identifier", image.id],
    ["Size", image.size],
    ["Grayscale", image.grayscale ? "on" : "off"],
    ["Blur", image.blur],
  ];
  for (const [label, value] of rows) {
    mount.append(
      el("dt", { textContent: label }),
      el("dd", { textContent: String(value) }),
    );
  }
}
