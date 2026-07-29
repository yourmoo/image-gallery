/*
 * Unit tests for the client's pure logic.
 *
 * The id arithmetic here is the browser's half of a rule the server also
 * implements (image_gallery/gallery.py). `tests/unit/python/test_gallery.py` asserts
 * the same ranges against the Python; the pair is what stops the two drifting,
 * which docs/adr/0020-ids-are-derived-in-the-browser.md names as the cost of
 * deriving ids client-side.
 *
 * Run: docker run --rm -v "${PWD}:/app" -w /app node:22-slim node --test "tests/unit/js/*.test.js"
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  imageIds,
  imageUrl,
  noticeMessages,
  pageUrl,
  pagination,
  readBounds,
  totalPages,
} from "../../../image_gallery/static/js/derive.js";

describe("imageIds", () => {
  it("gives the first ten images on page one", () => {
    assert.deepEqual(imageIds(1, 10, 100), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  });

  it("continues where the previous page ended", () => {
    // The off-by-one this arithmetic exists to get right (F2.6).
    assert.deepEqual(imageIds(2, 10, 100), [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
  });

  it("ends the last page at the catalogue bound", () => {
    assert.deepEqual(imageIds(10, 10, 100), [91, 92, 93, 94, 95, 96, 97, 98, 99, 100]);
  });

  it("covers every image exactly once across the catalogue", () => {
    // Stronger than checking a page or two: catches a fencepost error that
    // happens to be correct at the boundaries asserted above.
    const seen = [];
    for (let page = 1; page <= 10; page++) seen.push(...imageIds(page, 10, 100));

    assert.equal(seen.length, 100);
    assert.deepEqual(seen, Array.from({ length: 100 }, (_, i) => i + 1));
  });

  it("does not pad a short final page", () => {
    assert.deepEqual(imageIds(10, 10, 95), [91, 92, 93, 94, 95]);
  });

  it("returns nothing for a page past the end rather than wrapping", () => {
    // Validation should have rejected this, so it must not quietly succeed.
    assert.deepEqual(imageIds(11, 10, 100), []);
  });

  it("follows the chosen count", () => {
    assert.equal(imageIds(1, 20, 100).length, 20);
    assert.deepEqual(imageIds(2, 20, 100)[0], 21);
    assert.deepEqual(imageIds(2, 50, 100), Array.from({ length: 50 }, (_, i) => i + 51));
  });

  it("agrees with the server on every page of a 95-image catalogue", () => {
    // The awkward case: a catalogue that does not divide evenly. Mirrors
    // test_gallery.py's short-final-page assertions.
    const seen = [];
    for (let page = 1; page <= 10; page++) seen.push(...imageIds(page, 10, 95));

    assert.deepEqual(seen, Array.from({ length: 95 }, (_, i) => i + 1));
  });
});

describe("readBounds", () => {
  it("reads the three values the shell publishes", () => {
    assert.deepEqual(readBounds({ page: "2", count: "20", catalogueSize: "100" }), {
      page: 2,
      count: 20,
      catalogueSize: 100,
    });
  });

  it("rejects a dataset missing a value", () => {
    // The shell did not render what the client requires; failing visibly beats
    // rendering an empty grid that looks like an empty catalogue.
    assert.equal(readBounds({ page: "1", count: "10" }), null);
  });

  it("rejects values that are not positive integers", () => {
    assert.equal(readBounds({ page: "0", count: "10", catalogueSize: "100" }), null);
    assert.equal(readBounds({ page: "abc", count: "10", catalogueSize: "100" }), null);
    assert.equal(readBounds({ page: "1", count: "-5", catalogueSize: "100" }), null);
    assert.equal(readBounds({ page: "1", count: "10", catalogueSize: "" }), null);
  });
});

describe("imageUrl", () => {
  // The template is built by the server from a reversed route, so no path is
  // written in JavaScript (F5.2, F5.4). The client substitutes an id into it
  // and appends only the variations it holds in its own controls.
  const template = "/images/0";

  it("substitutes the id into the server-built template", () => {
    assert.equal(imageUrl(template, 7, {}), "/images/7");
  });

  it("points at this application, never at the provider", () => {
    // ADR 3: the browser must never learn picsum.dev exists.
    const url = imageUrl(template, 7, { size: "large" });

    assert.ok(url.startsWith("/images/"));
    assert.ok(!url.includes("picsum"));
    assert.ok(!url.includes("seed"));
  });

  it("carries a non-default size", () => {
    assert.equal(imageUrl(template, 7, { size: "large" }), "/images/7?size=large");
  });

  it("omits a size that is absent", () => {
    // A URL carrying only what was asked for keeps the browser cache and the
    // server cache keyed on the same small set of variations.
    assert.equal(imageUrl(template, 3, {}), "/images/3");
  });

  it("gives every image a distinct url so the browser caches them separately", () => {
    const urls = new Set([1, 2, 3].map((id) => imageUrl(template, id, {})));

    assert.equal(urls.size, 3);
  });
});

describe("totalPages", () => {
  // Mirrors total_pages in image_gallery/validation.py, case for case. The two
  // must agree or the client will offer a next link to a page the server
  // rejects.
  it("divides the catalogue by the page size", () => {
    assert.equal(totalPages(100, 10), 10);
    assert.equal(totalPages(100, 20), 5);
    assert.equal(totalPages(100, 50), 2);
  });

  it("rounds up for a short final page", () => {
    assert.equal(totalPages(95, 10), 10);
    assert.equal(totalPages(101, 10), 11);
  });

  it("gives an empty catalogue one page rather than none", () => {
    // Zero would make every page number invalid, including the default.
    assert.equal(totalPages(0, 10), 1);
  });
});

describe("pageUrl", () => {
  it("sets the page number", () => {
    assert.equal(pageUrl(3, new URLSearchParams()), "?page=3");
  });

  it("keeps the active size and filters", () => {
    // F2.3 — the most easily broken pagination requirement. Losing these on
    // page 2 is the classic gallery bug: filters silently reset as you page.
    const current = new URLSearchParams("size=large&grayscale=1&blur=4");
    const url = pageUrl(2, current);

    assert.ok(url.includes("size=large"));
    assert.ok(url.includes("grayscale=1"));
    assert.ok(url.includes("blur=4"));
    assert.ok(url.includes("page=2"));
  });

  it("replaces the existing page rather than appending a second one", () => {
    const url = pageUrl(5, new URLSearchParams("page=2&size=small"));

    assert.equal(url.match(/page=/g).length, 1);
    assert.ok(url.includes("page=5"));
  });

  it("drops a notice from the previous navigation", () => {
    // The banner explained a correction that has already been made; carrying
    // it to the next page would re-explain something the user has moved past.
    const url = pageUrl(2, new URLSearchParams("notice=invalid_page&size=large"));

    assert.ok(!url.includes("notice"));
    assert.ok(url.includes("size=large"));
  });
});

describe("pagination", () => {
  it("offers no previous link on the first page", () => {
    // Absence, not a disabled state: the Gherkin asserts the element is not
    // rendered at all (docs/ui/design-system.md § Pagination).
    const links = pagination(1, 10);

    assert.equal(links.previous, null);
    assert.equal(links.next, 2);
  });

  it("offers no next link on the last page", () => {
    const links = pagination(10, 10);

    assert.equal(links.previous, 9);
    assert.equal(links.next, null);
  });

  it("offers both in the middle", () => {
    const links = pagination(5, 10);

    assert.deepEqual([links.previous, links.next], [4, 6]);
  });

  it("offers neither when the collection fits on one page", () => {
    const links = pagination(1, 1);

    assert.equal(links.previous, null);
    assert.equal(links.next, null);
  });

  it("reports the position for the status text", () => {
    assert.equal(pagination(4, 7).status, "Page 4 of 7");
  });
});

describe("noticeMessages", () => {
  it("maps a token to the sentence a reader sees", () => {
    // The URL carries a token, not prose: wording is a UI concern and a
    // sentence in a query string would be unwieldy
    // (docs/adr/0006-recover-and-explain.md).
    assert.deepEqual(noticeMessages(["invalid_page"]), [
      "That page doesn't exist — showing page 1.",
    ]);
  });

  it("maps several tokens, because several parameters can be invalid at once", () => {
    assert.equal(noticeMessages(["invalid_page", "invalid_count"]).length, 2);
  });

  it("ignores a token it does not recognise", () => {
    // A hand-edited URL must not put arbitrary text on the page.
    assert.deepEqual(noticeMessages(["invalid_page", "<script>"]), [
      "That page doesn't exist — showing page 1.",
    ]);
  });

  it("returns nothing when there is nothing to say", () => {
    assert.deepEqual(noticeMessages([]), []);
  });
});
