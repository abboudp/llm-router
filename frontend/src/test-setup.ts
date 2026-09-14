import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";

// This project doesn't run vitest with `globals: true` (tests import
// describe/it/expect explicitly, matching the rest of the codebase), so
// Testing Library's automatic afterEach-cleanup detection never fires.
// Do it here instead, once, for every component test.
afterEach(() => {
  cleanup();
});

// jsdom doesn't implement scrollIntoView; Thread.tsx calls it to keep the
// latest message in view, so components that render it need a no-op stub.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// On newer Node versions, Node's own experimental native `localStorage`
// global (only functional with a `--localstorage-file` flag) shadows
// jsdom's polyfill, leaving `window.localStorage` undefined here. Give the
// test environment a minimal, real in-memory Storage so code (and tests)
// that use localStorage — e.g. the theme toggle — work the same as they
// would in a real browser.
if (typeof window !== "undefined" && !window.localStorage) {
  const backing = new Map<string, string>();
  const memoryStorage: Storage = {
    getItem: (key) => (backing.has(key) ? (backing.get(key) as string) : null),
    setItem: (key, value) => {
      backing.set(key, String(value));
    },
    removeItem: (key) => {
      backing.delete(key);
    },
    clear: () => {
      backing.clear();
    },
    key: (index) => Array.from(backing.keys())[index] ?? null,
    get length() {
      return backing.size;
    },
  };
  Object.defineProperty(window, "localStorage", {
    value: memoryStorage,
    writable: true,
    configurable: true,
  });
}
