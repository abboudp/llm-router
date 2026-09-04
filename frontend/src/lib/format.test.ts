import { describe, expect, it } from "vitest";
import { formatLatency } from "./format";

describe("formatLatency", () => {
  it("shows ms under a second", () => expect(formatLatency(842)).toBe("842 ms"));
  it("shows seconds with one decimal above a second", () =>
    expect(formatLatency(3187)).toBe("3.2 s"));
});
