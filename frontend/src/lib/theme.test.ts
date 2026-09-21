import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { applyTheme, getStoredTheme, resolveInitialTheme, setStoredTheme } from "./theme";

const STORAGE_KEY = "llm-router-theme";

describe("theme storage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("returns null when nothing has been stored", () => {
    expect(getStoredTheme()).toBeNull();
  });

  it("round-trips a stored theme", () => {
    setStoredTheme("dark");
    expect(getStoredTheme()).toBe("dark");
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe("dark");
  });

  it("ignores a garbage stored value", () => {
    window.localStorage.setItem(STORAGE_KEY, "solarized");
    expect(getStoredTheme()).toBeNull();
  });

  it("getStoredTheme returns null if localStorage throws", () => {
    // Spying on the method (rather than replacing `window.localStorage`
    // wholesale with vi.stubGlobal) avoids jsdom's non-configurable
    // getter-backed `localStorage` property.
    vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(getStoredTheme()).toBeNull();
  });

  it("setStoredTheme does not throw if localStorage is unavailable", () => {
    vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    expect(() => setStoredTheme("dark")).not.toThrow();
  });
});

describe("resolveInitialTheme", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("prefers an explicitly stored theme over system preference", () => {
    setStoredTheme("light");
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    expect(resolveInitialTheme()).toBe("light");
  });

  it("falls back to the system dark preference when nothing is stored", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    expect(resolveInitialTheme()).toBe("dark");
  });

  it("falls back to light when there is no stored theme and no dark preference", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    expect(resolveInitialTheme()).toBe("light");
  });

  it("falls back to light if matchMedia is unavailable", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(resolveInitialTheme()).toBe("light");
  });
});

describe("applyTheme", () => {
  afterEach(() => {
    document.documentElement.removeAttribute("data-theme");
  });

  it("sets the data-theme attribute on the document root", () => {
    applyTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    applyTheme("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});
