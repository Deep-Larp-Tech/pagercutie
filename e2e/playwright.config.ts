import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./tests",
  globalSetup: "./global-setup.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "html",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Brings up the whole stack from the repo root unless one already answers; CI starts it in its own step
  // (.github/workflows/e2e.yml), and a fresh runner never has a stale stack to reuse.
  webServer: {
    command: "docker compose up --wait",
    cwd: "..",
    url: baseURL,
    reuseExistingServer: true,
    timeout: 180_000,
  },
});
