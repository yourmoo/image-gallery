/*
 * Unit tests for the detail page's pure logic.
 *
 * These cover the decisions the page makes about URLs and about what to build
 * from a payload. The payload's *contents* are the server's business and are
 * tested in tests/unit/python/test_api_image.py — nothing here asserts what
 * `size` resolves to, only what the client does with the answer.
 *
 * `buildNotice` takes a document so it can be exercised without a browser; the
 * stub below implements the four methods it uses and nothing else.
 *
 * Run: docker run --rm -v "${PWD}:/app" -w /app node:22-slim node --test "tests/unit/js/*.test.js"
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  apiQuery,
  apiUrl,
  buildNotice,
  controlParameter,
  correctedSearch,
  searchForChange,
  sizeOptions,
} from "../../../image_gallery/static/js/detail-render.js";

/* The smallest thing `buildNotice` can build against: enough of the DOM to
 * record what was created, and nothing more. */
function fakeDocument() {
  const make = (tag) => ({
    tagName: tag.toUpperCase(),
    className: "",
    dataset: {},
    attributes: {},
    children: [],
    textContent: "",
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
  });
  return { createElement: make };
}

describe("apiQuery", () => {
  it("passes the gallery's parameters through", () => {
    assert.equal(apiQuery("?page=3&size=small"), "page=3&size=small");
  });

  it("drops notice, which the payload now carries itself", () => {
    assert.equal(apiQuery("?page=3&notice=invalid_size:huge"), "page=3");
  });

  it("survives an empty search", () => {
    assert.equal(apiQuery(""), "");
  });
});

describe("apiUrl", () => {
  it("substitutes the id into the reversed template", () => {
    assert.equal(apiUrl("/api/images/0", 7), "/api/images/7");
  });

  it("keeps the query when there is one", () => {
    assert.equal(apiUrl("/api/images/0", 7, "?size=small"), "/api/images/7?size=small");
  });

  it("replaces only the id placeholder, not a zero in the path", () => {
    assert.equal(apiUrl("/v0/api/images/0", 12), "/v0/api/images/12");
  });

  it("appends no question mark when there is nothing to ask", () => {
    assert.equal(apiUrl("/api/images/0", 7, ""), "/api/images/7");
  });
});

describe("correctedSearch", () => {
  it("leaves a clean URL alone", () => {
    assert.equal(correctedSearch("?size=small", []), null);
  });

  it("returns null when nothing needs changing", () => {
    assert.equal(correctedSearch("?page=2", undefined), null);
  });

  it("drops a rejected blur", () => {
    const notices = [{ code: "invalid_blur", value: "99" }];

    assert.equal(correctedSearch("?blur=99&page=2", notices), "?page=2");
  });

  it("drops every parameter that could carry a rejected size", () => {
    /* Both size controls feed the same validation, so a correction that
     * dropped only one of them left the bad value in the URL — which is what
     * made the old server-side version redirect to itself forever. */
    const notices = [{ code: "invalid_size", value: "3000x1000" }];
    const search = "?custom_detail_size=3000x1000&detail_size=large&page=2";

    assert.equal(correctedSearch(search, notices), "?page=2");
  });

  it("falls back to the path when nothing survives", () => {
    const notices = [{ code: "invalid_blur", value: "99" }];

    assert.equal(correctedSearch("?blur=99", notices, "/images/3"), "/images/3");
  });

  it("reports no change when the rejected parameter is not in the URL", () => {
    /* A notice can name a parameter the address bar never carried — a stale
     * link, say. Rewriting history for that would be a pointless entry. */
    const notices = [{ code: "invalid_blur", value: "99" }];

    assert.equal(correctedSearch("?page=2", notices), null);
  });
});

describe("buildNotice", () => {
  it("builds nothing when there is nothing to say", () => {
    /* A scenario asserts the banner is *absent*, not empty. */
    assert.equal(buildNotice([], fakeDocument()), null);
    assert.equal(buildNotice(undefined, fakeDocument()), null);
  });

  it("renders a single message as its own paragraph", () => {
    const banner = buildNotice([{ message: "that size is too big" }], fakeDocument());

    assert.equal(banner.tagName, "P");
    assert.equal(banner.className, "notice");
    assert.equal(banner.dataset.testid, "notice");
    assert.equal(banner.attributes.role, "status");
    assert.equal(banner.textContent, "that size is too big");
  });

  it("gathers several messages into one banner with a list", () => {
    const banner = buildNotice(
      [{ message: "bad size" }, { message: "bad blur" }],
      fakeDocument(),
    );

    assert.equal(banner.children.length, 1);
    const [list] = banner.children;
    assert.equal(list.tagName, "UL");
    assert.deepEqual(
      list.children.map((item) => item.textContent),
      ["bad size", "bad blur"],
    );
  });

  it("sets the message as text, never as markup", () => {
    /* The message quotes a value the user supplied, so treating it as HTML
     * would make `?size=<script>` an injection. */
    const nasty = '<script>alert(1)</script>';
    const banner = buildNotice([{ message: nasty }], fakeDocument());

    assert.equal(banner.textContent, nasty);
    assert.equal(banner.children.length, 0);
  });
});

describe("sizeOptions", () => {
  it("marks the active size", () => {
    assert.deepEqual(sizeOptions(["small", "medium", "large"], "medium"), [
      { value: "small", selected: false },
      { value: "medium", selected: true },
      { value: "large", selected: false },
    ]);
  });

  it("selects nothing for a custom size, which the list cannot hold", () => {
    const options = sizeOptions(["small", "medium", "large"], "1200x900");

    assert.equal(options.filter((o) => o.selected).length, 0);
  });
});

describe("controlParameter", () => {
  it("keeps a chosen named size", () => {
    assert.deepEqual(controlParameter("detail_size", "small"), ["detail_size", "small"]);
  });

  it("omits an empty custom size rather than sending a blank", () => {
    /* The empty control must not override the one the user actually set. */
    assert.equal(controlParameter("custom_detail_size", "   "), null);
  });

  it("trims a custom size", () => {
    assert.deepEqual(controlParameter("custom_detail_size", " 300x300 "), [
      "custom_detail_size",
      "300x300",
    ]);
  });

  it("sends grayscale only when it is on", () => {
    assert.deepEqual(controlParameter("grayscale", true), ["grayscale", "1"]);
    assert.equal(controlParameter("grayscale", false), null);
  });

  it("omits a zero blur, keeping the URL short", () => {
    assert.deepEqual(controlParameter("blur", "4"), ["blur", "4"]);
    assert.equal(controlParameter("blur", "0"), null);
  });

  it("ignores a control it does not know", () => {
    assert.equal(controlParameter("nonsense", "x"), null);
  });
});

describe("searchForChange", () => {
  it("carries the gallery's state so the back link survives", () => {
    const search = searchForChange("?page=3&count=25&size=small", {
      detail_size: "medium",
    });
    const params = new URLSearchParams(search);

    assert.equal(params.get("page"), "3");
    assert.equal(params.get("count"), "25");
    assert.equal(params.get("size"), "small");
    assert.equal(params.get("detail_size"), "medium");
  });

  it("replaces the previous choice rather than accumulating", () => {
    const search = searchForChange("?detail_size=small", { detail_size: "large" });

    assert.equal(new URLSearchParams(search).getAll("detail_size").length, 1);
  });

  it("drops a stale notice", () => {
    const search = searchForChange("?notice=invalid_size:huge", { detail_size: "large" });

    assert.equal(new URLSearchParams(search).has("notice"), false);
  });

  it("clears the custom size when the select is used instead", () => {
    const search = searchForChange("?custom_detail_size=300x300", {
      detail_size: "large",
      custom_detail_size: "",
    });

    assert.equal(new URLSearchParams(search).has("custom_detail_size"), false);
  });

  it("returns an empty string when everything is at its default", () => {
    assert.equal(searchForChange("", { blur: "0", grayscale: false }), "");
  });
});
