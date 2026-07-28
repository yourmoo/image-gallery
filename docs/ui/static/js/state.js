// state.js — URL <-> state. The single source of truth.
// Only module that touches history. See design-system.md §3.

export const DEFAULTS = Object.freeze({
  page: 1,
  size: "medium",
  grayscale: false,
  blur: 0,
  count: 10,
});

const SIZES = ["small", "medium", "large"];
const COUNTS = [10, 20, 50];
const CUSTOM_SIZE = /^(\d{2,4})x(\d{2,4})$/; // ADR 10

// Validation mirrors the server's allow-lists: a hand-edited URL bypasses
// every widget, so the client must not trust its own query string either.
// Returns { state, notices } — an invalid parameter never discards the
// good ones alongside it (Scenario: A valid filter survives an invalid one).
export function read(search = location.search) {
  const q = new URLSearchParams(search);
  const state = { ...DEFAULTS };
  const notices = [];

  if (q.has("size")) {
    const raw = q.get("size");
    if (SIZES.includes(raw) || CUSTOM_SIZE.test(raw)) state.size = raw;
    else notices.push(`'${raw}' is not a valid size — showing ${DEFAULTS.size}.`);
  }

  if (q.has("grayscale")) {
    state.grayscale = ["1", "true", "on"].includes(q.get("grayscale"));
  }

  if (q.has("blur")) {
    const n = Number(q.get("blur"));
    if (Number.isInteger(n) && n >= 0 && n <= 10) state.blur = n;
    else notices.push(`'${q.get("blur")}' is out of range for blur — showing ${DEFAULTS.blur}.`);
  }

  if (q.has("count")) {
    const n = Number(q.get("count"));
    if (COUNTS.includes(n)) state.count = n;
    else notices.push(`'${q.get("count")}' is not a valid count — showing ${DEFAULTS.count}.`);
  }

  if (q.has("page")) {
    const n = Number(q.get("page"));
    if (Number.isInteger(n) && n >= 1) state.page = n;
    else notices.push("That page doesn't exist — showing page 1.");
  }

  // ?notice= carries a message across the first load only.
  if (q.has("notice")) notices.push(q.get("notice"));

  return { state, notices };
}

// Defaults are omitted, so a shared URL stays short and readable.
export function toQuery(state) {
  const q = new URLSearchParams();
  if (state.page !== DEFAULTS.page) q.set("page", state.page);
  if (state.size !== DEFAULTS.size) q.set("size", state.size);
  if (state.grayscale) q.set("grayscale", "1");
  if (state.blur !== DEFAULTS.blur) q.set("blur", state.blur);
  if (state.count !== DEFAULTS.count) q.set("count", state.count);
  const s = q.toString();
  return s ? `?${s}` : location.pathname;
}

// pushState on intent (a control change, a page link).
export function write(state) {
  history.pushState({ ...state }, "", toQuery(state));
}

// replaceState on correction — clamping an invalid page must not leave a
// bad entry to go Back to.
export function correct(state) {
  history.replaceState({ ...state }, "", toQuery(state));
}

export function isDefault(state, key) {
  return state[key] === DEFAULTS[key];
}

// Grid cell floor for a custom WxH size, clamped to sane bounds.
export function customCellFloor(size) {
  const m = CUSTOM_SIZE.exec(size);
  if (!m) return null;
  return `${Math.min(320, Math.max(110, Number(m[1])))}px`;
}
