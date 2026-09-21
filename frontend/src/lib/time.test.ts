import { describe, expect, it } from "vitest";
import { relativeTime } from "./time";

describe("relativeTime", () => {
  const now = 1_700_000_000;

  it("shows 'just now' for timestamps under a minute old", () => {
    expect(relativeTime(now - 5, now)).toBe("just now");
    expect(relativeTime(now - 59, now)).toBe("just now");
  });

  it("shows minutes ago under an hour", () => {
    expect(relativeTime(now - 60, now)).toBe("1m ago");
    expect(relativeTime(now - 120, now)).toBe("2m ago");
    expect(relativeTime(now - 59 * 60, now)).toBe("59m ago");
  });

  it("shows hours ago under a day", () => {
    expect(relativeTime(now - 3600, now)).toBe("1h ago");
    expect(relativeTime(now - 3 * 3600, now)).toBe("3h ago");
    expect(relativeTime(now - 23 * 3600, now)).toBe("23h ago");
  });

  it("shows 'yesterday' for one to two days old", () => {
    expect(relativeTime(now - 25 * 3600, now)).toBe("yesterday");
    expect(relativeTime(now - 47 * 3600, now)).toBe("yesterday");
  });

  it("shows days ago beyond two days", () => {
    expect(relativeTime(now - 3 * 86400, now)).toBe("3d ago");
    expect(relativeTime(now - 10 * 86400, now)).toBe("10d ago");
  });

  it("clamps future timestamps to 'just now' instead of going negative", () => {
    expect(relativeTime(now + 500, now)).toBe("just now");
  });

  it("defaults `now` to the current time when omitted", () => {
    const nowSeconds = Date.now() / 1000;
    expect(relativeTime(nowSeconds - 1)).toBe("just now");
  });
});
