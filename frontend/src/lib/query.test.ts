import { describe, expect, it } from "vitest";
import { withQuery } from "./query";

describe("withQuery", () => {
  it("returns the bare path when there are no params", () => {
    expect(withQuery("/v1/conversations", {})).toBe("/v1/conversations");
  });

  it("skips undefined values", () => {
    expect(withQuery("/v1/conversations", { q: undefined })).toBe("/v1/conversations");
  });

  it("skips empty-string values", () => {
    expect(withQuery("/v1/conversations", { q: "" })).toBe("/v1/conversations");
  });

  it("appends a single param", () => {
    expect(withQuery("/v1/conversations", { q: "kubernetes" })).toBe(
      "/v1/conversations?q=kubernetes",
    );
  });

  it("appends multiple params, keeping only the ones with values", () => {
    expect(withQuery("/x", { limit: 20, before: undefined })).toBe("/x?limit=20");
    expect(withQuery("/x", { limit: 20, before: "m1" })).toBe("/x?limit=20&before=m1");
  });

  it("URL-encodes special characters in values", () => {
    expect(withQuery("/v1/conversations", { q: "a b/c" })).toBe("/v1/conversations?q=a+b%2Fc");
  });

  it("stringifies numeric values", () => {
    expect(withQuery("/x", { limit: 5 })).toBe("/x?limit=5");
  });
});
