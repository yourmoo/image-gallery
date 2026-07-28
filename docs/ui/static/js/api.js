// api.js — fetches JSON from Django. One in-flight request at a time.
// Every URL here is a Django URL; picsum.dev never appears client-side.

import { toQuery } from "./state.js";

let inFlight = null;

export class Unreachable extends Error {}

// Aborts the previous request, so fast filter changes can't land out of order.
export async function fetchImages(state) {
  if (inFlight) inFlight.abort();
  const controller = new AbortController();
  inFlight = controller;

  try {
    const res = await fetch(`/api/images/${toQuery(state)}`, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });

    if (res.status === 503) throw new Unreachable("Image service unreachable");
    if (!res.ok) throw new Error(`API returned ${res.status}`);

    // Expected payload:
    // { images: [{ id, url, width, height }], page, total_pages,
    //   notices: [], degraded: false, cached_at: null }
    return await res.json();
  } finally {
    if (inFlight === controller) inFlight = null;
  }
}

// Detail view (F4.4). Reports what was actually used, which can differ
// from the gallery's own size.
export async function fetchImage(id) {
  const res = await fetch(`/api/images/${id}/`, { headers: { Accept: "application/json" } });
  if (res.status === 503) throw new Unreachable("Image service unreachable");
  if (!res.ok) throw new Error(`API returned ${res.status}`);
  return res.json();
}
