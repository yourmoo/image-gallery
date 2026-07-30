/*
 * The detail page's decisions, as pure functions.
 *
 * Everything here takes a payload from `/api/images/<id>` and returns plain
 * data or a detached DOM node. Nothing queries the document or listens for an
 * event — that is detail-panel.js's job. The split is the same one gallery.js
 * and derive.js already use, and it exists so these can be unit-tested without
 * a browser (tests/unit/js/detail-render.test.js).
 *
 * The payload is the single source of truth for what the page shows. In
 * particular the **notice sentences arrive already written**: the wording lives
 * in image_gallery/validation.py, where it can quote configured bounds like
 * "between 16 and 1600". A copy here would go stale the moment those settings
 * were retuned, which is exactly how the old copy came to say "showing medium"
 * on a page that shows large.
 */

/* The query string that asks the API for what the address bar is showing.
 *
 * Passed through rather than rebuilt: the gallery's own parameters (`page`,
 * `count`, `size`) ride along so the API can compute a back link that restores
 * the grid the user left (F4.1). Only `notice` is dropped — it was the old
 * redirect's way of carrying an explanation between requests, and the payload
 * now carries its own.
 */
export function apiQuery(search) {
  const params = new URLSearchParams(search);
  params.delete("notice");
  return params.toString();
}

/* The API URL for one image, from the template the shell reversed.
 *
 * The template has a `0` where the id goes, matching how the gallery builds
 * its own URLs — no path is written in JavaScript (F5.4).
 */
export function apiUrl(template, id, search = "") {
  const path = template.replace(/0(?=[^0]*$)/, String(id));
  const query = apiQuery(search);
  return query ? `${path}?${query}` : path;
}

/* The address bar, cleaned of anything the server rejected.
 *
 * A rejected value is dropped rather than corrected to something the user did
 * not choose, so the URL reflects what is actually being shown. Returns null
 * when nothing needs changing, so the caller can skip a needless history
 * write.
 *
 * This is the "redirect" the requirement asks for — the user is moved off the
 * bad URL and told why. It never needed to be a 3xx, and doing it here costs
 * no round trip.
 */
export function correctedSearch(search, notices, pathname = "") {
  if (!notices || notices.length === 0) return null;

  const params = new URLSearchParams(search);
  let changed = false;

  for (const notice of notices) {
    /* `invalid_size` covers both size controls, because either can carry the
     * offending value. Dropping only one of them is what made the old
     * server-side correction redirect to itself forever. */
    const names =
      notice.code === "invalid_size"
        ? ["custom_detail_size", "detail_size", "size"]
        : [notice.code.replace(/^invalid_/, "")];

    for (const name of names) {
      if (params.has(name)) {
        params.delete(name);
        changed = true;
      }
    }
  }

  if (!changed) return null;
  const query = params.toString();
  /* `pathname` rather than "" when nothing is left: assigning an empty string
   * to replaceState would keep the old query. The caller passes the current
   * path; the default keeps this function usable without a document. */
  return query ? `?${query}` : pathname;
}

/* The notice banner, or null when there is nothing to say.
 *
 * Null rather than an empty element: a scenario asserts the banner is *absent*
 * when no parameter was rejected, and an always-present empty <p> would fail
 * it as well as read as a blank box to anyone using a screen reader.
 *
 * The message is set as `textContent`, never as markup. It contains a value the
 * user supplied, so treating it as HTML would make `?size=<script>` an
 * injection — the same reason the server escapes it.
 */
export function buildNotice(notices, doc = document) {
  if (!notices || notices.length === 0) return null;

  const banner = doc.createElement("p");
  banner.className = "notice";
  banner.dataset.testid = "notice";
  banner.setAttribute("role", "status");

  if (notices.length === 1) {
    banner.textContent = notices[0].message;
    return banner;
  }

  /* Several parameters can be invalid at once — one banner, one list
   * (docs/ui/design-system.md § Notice banner). */
  const list = doc.createElement("ul");
  list.className = "notice__list";
  for (const notice of notices) {
    const item = doc.createElement("li");
    item.textContent = notice.message;
    list.appendChild(item);
  }
  banner.appendChild(list);
  return banner;
}

/* The size <select>'s options, with the active one marked.
 *
 * A custom size is not in the list and cannot be: `WxH` is unbounded. The
 * select simply shows nothing selected, and the text beside it reports the
 * resolved value — which is why that readout is part of the contract rather
 * than decoration (F4.4).
 */
export function sizeOptions(namedSizes, active) {
  return namedSizes.map((name) => ({ value: name, selected: name === active }));
}

/* How a control's value becomes a query parameter.
 *
 * The custom-size field and the select write to *different* parameters, so an
 * empty one cannot override the other. `null` means "leave this out entirely",
 * which is how a default keeps the URL short.
 */
export function controlParameter(name, value) {
  switch (name) {
    case "detail_size":
      return value ? ["detail_size", value] : null;
    case "custom_detail_size":
      return value.trim() ? ["custom_detail_size", value.trim()] : null;
    case "grayscale":
      return value ? ["grayscale", "1"] : null;
    case "blur":
      return Number(value) > 0 ? ["blur", String(value)] : null;
    default:
      return null;
  }
}

/* The search string for a control change, preserving the gallery's state.
 *
 * `page`, `count` and the gallery's `size` are carried so the back link still
 * restores the grid the user came from. The detail page's own size parameters
 * are rewritten from the control that changed, and `notice` is dropped because
 * the next payload will bring its own.
 */
export function searchForChange(search, changes) {
  const params = new URLSearchParams(search);

  for (const name of ["detail_size", "custom_detail_size", "grayscale", "blur", "notice"]) {
    params.delete(name);
  }

  for (const [name, value] of Object.entries(changes)) {
    const pair = controlParameter(name, value);
    if (pair) params.set(pair[0], pair[1]);
  }

  const query = params.toString();
  return query ? `?${query}` : "";
}
