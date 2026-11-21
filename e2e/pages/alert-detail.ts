import type { Locator, Page } from "@playwright/test";

/** The alert detail at `/alerts/<id>`: the alert, its runbook steps, deliveries and history. */
export class AlertDetailPage {
  readonly steps: Locator;
  readonly noRunbook: Locator;
  readonly deliveries: Locator;
  readonly history: Locator;
  readonly notFound: Locator;
  readonly approveDialog: Locator;

  constructor(readonly page: Page) {
    this.steps = page.getByRole("list", { name: "Runbook steps" });
    this.noRunbook = page.getByRole("heading", { name: "No runbook for this alert" });
    this.deliveries = page.getByRole("table", { name: "Deliveries" });
    this.history = page.getByRole("list", { name: "History" });
    this.notFound = page.getByRole("heading", { name: "Page not found" });
    this.approveDialog = page.getByRole("alertdialog");
  }

  /** Opens the detail of alert `alertId`. */
  async goto(alertId: string): Promise<void> {
    await this.page.goto(`/alerts/${alertId}`);
  }

  /** The alert's title, the page's only `h1`. */
  title(title: string): Locator {
    return this.page.getByRole("heading", { level: 1, name: title });
  }

  /** Step `number` (from 1) of the runbook run. */
  step(number: number): Locator {
    return this.steps.getByRole("listitem", { name: new RegExp(`^Step ${number}:`) });
  }

  /** A decision button (`Approve step`, `Reject step`, `Yes`, `No`, `Mark as done`) on step `number`. */
  decision(number: number, label: string): Locator {
    return this.step(number).getByRole("button", { name: label, exact: true });
  }

  /** The history entry whose text matches `text`, e.g. "You: Acknowledged the alert". */
  historyEntry(text: string | RegExp): Locator {
    return this.history.getByRole("listitem").filter({ hasText: text });
  }
}
