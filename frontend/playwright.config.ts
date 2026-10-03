import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running Mana Career stack (by default the
 * production Compose stack behind nginx: `docker compose -f compose.prod.yml
 * up -d`, seeded with `python -m app.seed all`). CI runs them in the
 * `images` job; see docs/runbook.md for running them locally.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://localhost",
    // The CI stack uses a throwaway self-signed certificate.
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, grepInvert: /@phone/ },
    { name: "phone", use: { ...devices["Pixel 7"] }, grep: /@phone/ },
  ],
});
