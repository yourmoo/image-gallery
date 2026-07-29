/*
 * The client's pure logic: arithmetic and mapping, no DOM.
 *
 * Split from gallery.js so it can be unit-tested without a browser
 * (tests/unit/js/derive.test.js). That is a design constraint rather than a testing
 * convenience — logic reachable only through a rendered document is logic that
 * cannot be checked cheaply.
 *
 * `imageIds` is the browser's half of a rule the server also implements, in
 * image_gallery/gallery.py. The two must agree: this side decides what to
 * render, that side decides what is in range, and a divergence would show as
 * tiles requesting ids the server rejects. Both halves are tested against the
 * same cases (docs/adr/0020-ids-are-derived-in-the-browser.md).
 *
 * Plain ESM, loaded directly by the browser and by node --test. Nothing
 * transforms it, so what ships is what was tested.
 */

/* The id range for a page, clamped at the catalogue's end.
 *
 * A short final page carries what remains rather than being padded, and a page
 * past the end yields nothing rather than wrapping — validation should have
 * rejected that, so arithmetic which quietly succeeded would hide the failure
 * instead of surfacing it. */
export function imageIds(page, count, catalogueSize) {
  const first = (page - 1) * count + 1;
  if (first > catalogueSize) return [];

  const last = Math.min(first + count - 1, catalogueSize);
  const ids = [];
  for (let id = first; id <= last; id++) ids.push(id);
  return ids;
}

/* Parse the bounds the shell published, or null if any is unusable.
 *
 * All three are required. Returning null rather than substituting a default
 * keeps a missing value visible: a client that guessed `catalogueSize` would
 * render a plausible grid built on a number the server never sent. */
export function readBounds(dataset) {
  const parse = (raw) => {
    if (raw === undefined || raw === null || String(raw).trim() === "") return null;
    const value = Number(raw);
    return Number.isInteger(value) && value > 0 ? value : null;
  };

  const page = parse(dataset.page);
  const count = parse(dataset.count);
  const catalogueSize = parse(dataset.catalogueSize);

  if (page === null || count === null || catalogueSize === null) return null;
  return { page, count, catalogueSize };
}

/* How many pages a catalogue of this size yields at this page size.
 *
 * Mirrors `total_pages` in image_gallery/validation.py. At least 1: an empty
 * catalogue still has a page 1 to render, and returning 0 would make every
 * page number invalid including the default. */
export function totalPages(catalogueSize, count) {
  if (count <= 0) return 1;
  return Math.max(1, Math.ceil(catalogueSize / count));
}

/* The URL for another page, keeping whatever is currently active.
 *
 * F2.3: size, grayscale, and blur survive the move. Losing them on page 2 is
 * the classic gallery bug — filters that silently reset as you page — and it
 * is why the Gherkin asserts on the link's href rather than on where it lands.
 *
 * `notice` is deliberately dropped: it explained a correction that has already
 * happened, and carrying it forward would re-explain something the user has
 * moved past. */
export function pageUrl(page, currentParams) {
  const params = new URLSearchParams(currentParams);
  params.set("page", String(page));
  params.delete("notice");
  return `?${params.toString()}`;
}

/* Which pagination links exist, and the position to display.
 *
 * Returns `null` for an end rather than a flag, because the design system
 * renders no element at all there — the Gherkin asserts absence, not a
 * disabled state (docs/ui/design-system.md § Pagination). */
export function pagination(page, pages) {
  return {
    previous: page > 1 ? page - 1 : null,
    next: page < pages ? page + 1 : null,
    status: `Page ${page} of ${pages}`,
  };
}

/* The URL for one tile's image.
 *
 * `template` is built by the server by reversing the `image` route, so no path
 * is written here — the client only substitutes an id and appends the
 * variations its own controls hold (F5.2, F5.4). It points at this
 * application; the browser never contacts the provider
 * (docs/adr/0003-django-as-image-proxy.md).
 *
 * Parameters left at their defaults are omitted, so the browser cache and the
 * server cache stay keyed on the same small set of variations rather than on
 * URLs that differ only in redundant text.
 */
export function imageUrl(template, id, variations) {
  const path = template.replace(/0(?=[^0]*$)/, String(id));

  const query = new URLSearchParams();
  if (variations.size) query.set("size", variations.size);
  if (variations.grayscale) query.set("grayscale", "1");
  if (variations.blur) query.set("blur", String(variations.blur));

  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}

/* The active filters, as removable chips.
 *
 * A summary of what is currently applied, each with a link that clears just
 * that one parameter (docs/ui/design-system.md § Controls). Only non-default
 * values appear: a chip for every parameter would be a second, noisier copy of
 * the controls bar rather than a summary of it.
 *
 * `page` and `count` are excluded because they are not filters — they change
 * *which* images are shown, not how any image looks. Removing a filter also
 * returns to page 1, since the page a user was on rarely survives a change to
 * what is being paged through.
 */
const FILTERS = [
  { parameter: "size", label: (v) => `size ${v}`, isDefault: (v) => v === "medium" },
  { parameter: "grayscale", label: () => "grayscale on", isDefault: (v) => !v || v === "0" },
  { parameter: "blur", label: (v) => `blur ${v}`, isDefault: (v) => !v || v === "0" },
];

export function activeFilters(params) {
  return FILTERS.flatMap(({ parameter, label, isDefault }) => {
    const value = params.get(parameter);
    if (value === null || value === "" || isDefault(value)) return [];

    const without = new URLSearchParams(params);
    without.delete(parameter);
    without.delete("page");
    without.delete("notice");

    const query = without.toString();
    return [{
      parameter,
      value,
      label: label(value),
      removeUrl: query ? `?${query}` : "?",
    }];
  });
}

/* The wording behind each `?notice=` token.
 *
 * The URL carries a token so the address stays short and the phrasing stays a
 * UI concern (docs/adr/0006-recover-and-explain.md). Unrecognised tokens are
 * dropped rather than displayed, so a hand-edited URL cannot put arbitrary
 * text on the page. */
const NOTICES = {
  invalid_page: (value) =>
    value
      ? `"${value}" isn't a page in this collection — showing page 1.`
      : "That page doesn't exist — showing page 1.",
  invalid_count: (value) =>
    value
      ? `"${value}" isn't an available image count — showing 10 per page.`
      : "That image count isn't available — showing 10 per page.",
  invalid_size: (value) =>
    value
      ? `"${value}" isn't a valid size — showing medium.`
      : "That size isn't valid — showing medium.",
  invalid_grayscale: (value) =>
    value
      ? `"${value}" isn't a valid grayscale setting — showing colour.`
      : "That grayscale setting isn't valid — showing colour.",
  invalid_blur: (value) =>
    value
      ? `"${value}" isn't a valid blur — showing none.`
      : "That blur isn't valid — showing none.",
};

/* Turn `?notice=` tokens into the sentences a reader sees.
 *
 * A token may carry the rejected value after a colon — `invalid_size:huge` —
 * because F3.6 is about *explaining* the fallback, and a banner that said only
 * "something was wrong" would tell the user nothing about which parameter was
 * ignored. The value is percent-encoded in the URL and decoded here.
 *
 * Unrecognised tokens are dropped rather than displayed, so a hand-edited URL
 * cannot put arbitrary text on the page. The value is inserted as text
 * content, never as markup, so even a recognised token cannot inject anything.
 */
export function noticeMessages(tokens) {
  return tokens
    .map((token) => {
      const separator = token.indexOf(":");
      const name = separator === -1 ? token : token.slice(0, separator);
      const raw = separator === -1 ? "" : token.slice(separator + 1);

      const template = NOTICES[name];
      if (!template) return null;

      let value = raw;
      try {
        value = decodeURIComponent(raw);
      } catch {
        // A malformed escape sequence — show it as written rather than throw.
      }
      return template(value);
    })
    .filter(Boolean);
}
