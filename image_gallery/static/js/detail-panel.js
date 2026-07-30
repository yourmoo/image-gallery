/*
 * The detail page client: DOM wiring only.
 *
 * Every decision is delegated to detail-render.js, which is pure and
 * unit-tested. What is left here needs a document — fetching, inserting,
 * listening — and is covered by the browser tier.
 *
 * The page is a shell (docs/adr/0022-the-detail-page-joins-the-client.md).
 * This fetches `/api/images/<id>`, fills the controls and readouts from the
 * payload, and re-fetches when a control changes. Nothing navigates: a change
 * is a fetch and a re-render, which is what makes the controls apply instantly
 * the way the gallery's do (docs/ui/ui-notes.md).
 */

import {
  apiUrl,
  buildNotice,
  correctedSearch,
  searchForChange,
  sizeOptions,
} from "./detail-render.js";

const root = document.querySelector('[data-testid="detail"]');

if (root) {
  const imageId = root.dataset.imageId;
  const template = root.dataset.apiUrlTemplate;

  const image = root.querySelector('[data-testid="detail-image"]');
  const back = document.querySelector('[data-testid="back-to-gallery"]');
  const sizeControl = root.querySelector('[data-testid="size-control"]');
  const customSize = root.querySelector('[data-testid="custom-size-control"]');
  const grayscale = root.querySelector('[data-testid="grayscale-control"]');
  const blur = root.querySelector('[data-testid="blur-control"]');
  const sizeValue = root.querySelector('[data-testid="size-value"]');
  const grayscaleValue = root.querySelector('[data-testid="grayscale-value"]');
  const blurValue = root.querySelector('[data-testid="blur-value"]');

  /* Replaces the banner rather than appending: a re-render after a control
   * change must not stack a second explanation on top of the first. */
  function showNotices(notices) {
    const existing = document.querySelector('[data-testid="notice"]');
    if (existing) existing.remove();

    const banner = buildNotice(notices);
    if (banner) root.parentNode.insertBefore(banner, root);
  }

  function render(payload) {
    image.src = payload.url;
    image.alt = `Image ${payload.id}`;
    back.href = payload.backUrl;

    sizeControl.replaceChildren();
    for (const { value, selected } of sizeOptions(payload.namedSizes, payload.size)) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      option.selected = selected;
      sizeControl.appendChild(option);
    }

    /* The resolved value as text. A select cannot display a custom size, so
     * this readout is the report (F4.4) as much as the control is the setter. */
    sizeValue.textContent = payload.size;
    customSize.value = payload.customSize;
    grayscale.checked = payload.grayscale;
    grayscaleValue.textContent = payload.grayscale ? "on" : "off";
    blur.max = String(payload.maxBlur);
    blur.value = String(payload.blur);
    blurValue.textContent = String(payload.blur);

    showNotices(payload.notices);

    /* Drop rejected parameters from the address bar, so a reload does not ask
     * for the same impossible thing again. `replaceState` rather than a
     * navigation: the correction is already rendered, and pushing an entry
     * would put the bad URL in the back button. */
    const corrected = correctedSearch(
      window.location.search,
      payload.notices,
      window.location.pathname,
    );
    if (corrected !== null) {
      window.history.replaceState(null, "", corrected);
    }

    root.dataset.state = "ready";
  }

  async function load(search) {
    root.dataset.state = "loading";
    const response = await fetch(apiUrl(template, imageId, search), {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      /* The shell already 404s for an id outside the catalogue, so reaching
       * here means the API failed for a reason the page cannot fix. Say so
       * rather than leaving an empty frame that looks like it is still
       * loading — a failed state must never resemble a pending one. */
      root.dataset.state = "failed";
      return;
    }
    render(await response.json());
  }

  function apply(changes) {
    const search = searchForChange(window.location.search, changes);
    /* The address bar tracks what is shown, so the page can be bookmarked and
     * reloaded — but the change is applied by fetching, not by navigating. */
    window.history.replaceState(null, "", search || window.location.pathname);
    load(search);
  }

  function currentChanges() {
    return {
      detail_size: sizeControl.value,
      custom_detail_size: customSize.value,
      grayscale: grayscale.checked,
      blur: blur.value,
    };
  }

  for (const control of [sizeControl, customSize, grayscale, blur]) {
    control.addEventListener("change", () => apply(currentChanges()));
  }

  /* The readout beside the slider tracks the drag, so the number moves with
   * the thumb even though nothing is fetched until release. */
  blur.addEventListener("input", () => {
    blurValue.textContent = blur.value;
  });

  load(window.location.search);
}
