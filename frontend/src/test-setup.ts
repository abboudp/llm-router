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
