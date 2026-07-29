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

/* The wording behind each `?notice=` token.
 *
 * The URL carries a token so the address stays short and the phrasing stays a
 * UI concern (docs/adr/0006-recover-and-explain.md). Unrecognised tokens are
 * dropped rather than displayed, so a hand-edited URL cannot put arbitrary
 * text on the page. */
const NOTICES = {
  invalid_page: "That page doesn't exist — showing page 1.",
  invalid_count: "That image count isn't available — showing 10 per page.",
};

export function noticeMessages(tokens) {
  return tokens.map((token) => NOTICES[token]).filter(Boolean);
}
