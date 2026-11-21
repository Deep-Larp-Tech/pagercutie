import { test } from "@playwright/test";

/** Origin of Mailpit's web UI and HTTP API, which catches the email deliveries (compose publishes it on :8025). */
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

/** The parts of a Mailpit message the specs check. */
export interface MailpitMessage {
  subject: string;
  to: string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseMessage(value: unknown): MailpitMessage {
  if (!isRecord(value) || typeof value.Subject !== "string" || !Array.isArray(value.To)) {
    throw new Error(`Unexpected Mailpit message: ${JSON.stringify(value)}`);
  }
  const to = value.To.map((recipient: unknown) => {
    if (!isRecord(recipient) || typeof recipient.Address !== "string") {
      throw new Error(`Unexpected Mailpit recipient: ${JSON.stringify(recipient)}`);
    }
    return recipient.Address;
  });
  return { subject: value.Subject, to };
}

/** Skips the current test when Mailpit does not answer, e.g. a stack started without it. */
export async function requireMailpit(): Promise<void> {
  const reachable = await fetch(new URL("/api/v1/info", MAILPIT_URL)).then(
    (response) => response.ok,
    () => false,
  );
  test.skip(!reachable, `Mailpit does not answer at ${MAILPIT_URL}; set E2E_MAILPIT_URL`);
}

/** The messages Mailpit holds for `address`, newest first. */
export async function emailsTo(address: string): Promise<MailpitMessage[]> {
  const url = new URL("/api/v1/search", MAILPIT_URL);
  url.searchParams.set("query", `to:"${address}"`);
  const response = await fetch(url);
  if (!response.ok) throw new Error(`GET ${url} answered ${response.status}`);
  const body: unknown = await response.json();
  if (!isRecord(body) || !Array.isArray(body.messages)) {
    throw new Error(`Unexpected Mailpit search answer: ${JSON.stringify(body)}`);
  }
  return body.messages.map(parseMessage);
}
