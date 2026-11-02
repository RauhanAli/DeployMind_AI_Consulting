import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against a running stack (API + worker + web) seeded with demo data:
 *   python -m app.seed.demo --reset   (apps/api)
 *   pnpm --filter @deploymind/web e2e
 * The suite signs in many times; run the API with AUTH_RATE_LIMIT_PER_MINUTE raised (e.g. 500) or logins will be
 * rate limited exactly as they would be in production.
 * Override the target with E2E_BASE_URL.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /public\.spec\.ts/ },
  ],
});
