import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  retries: 0,
  // All spec files share one live backend process and SQLite database (see
  // scripts/run_e2e.sh), so different spec files can't safely run as
  // concurrent workers — a test in one file would see conversations created
  // by a test running at the same time in another file. One worker keeps
  // the whole suite deterministic.
  workers: 1,
  use: {
    baseURL: "http://localhost:8000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
