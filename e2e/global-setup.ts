import type { FullConfig } from "@playwright/test";

const TIMEOUT_MS = 60_000;
const INTERVAL_MS = 1_000;

/** Waits until the API answers `GET /api/health` with 200 through the frontend proxy, so specs never race startup. */
export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL;
  if (baseURL === undefined) throw new Error("playwright.config.ts sets no baseURL");
  const url = new URL("/api/health", baseURL).toString();
  const deadline = Date.now() + TIMEOUT_MS;
  let last = "no answer";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.status === 200) return;
      last = `HTTP ${response.status}`;
    } catch (error) {
      last = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, INTERVAL_MS));
  }
  throw new Error(
    `${url} did not answer 200 within ${TIMEOUT_MS / 1000} s (last: ${last}). ` +
      "Start the stack with `mise run stack` or point E2E_BASE_URL at a running one.",
  );
}
