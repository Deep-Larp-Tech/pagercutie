import type { Locator, Page } from "@playwright/test";

/** A live alert feed: `/teams/<slug>/alerts` with filters, or the open alerts on the Overview. */
export class AlertFeed {
  readonly cards: Locator;
  readonly statusFilter: Locator;
  readonly severityFilter: Locator;
  readonly emptyState: Locator;
  readonly connectionBar: Locator;

  constructor(readonly page: Page) {
    this.cards = page.getByRole("article");
    this.statusFilter = page.getByRole("group", { name: "Status" });
    this.severityFilter = page.getByRole("group", { name: "Severity" });
    this.emptyState = page.getByRole("heading", { name: /^No (open alerts|alerts match these filters)$/ });
    this.connectionBar = page.getByRole("status").filter({ hasText: /Reconnecting…|Live updates paused/ });
  }

  /** Opens the team's feed. */
  async goto(teamSlug: string): Promise<void> {
    await this.page.goto(`/teams/${teamSlug}/alerts`);
  }

  /** The card whose title is `title`. */
  card(title: string): Locator {
    return this.page.getByRole("article", { name: title });
  }

  /** The Acknowledge button on the card titled `title`. */
  acknowledgeButton(title: string): Locator {
    return this.card(title).getByRole("button", { name: "Acknowledge" });
  }

  /** The Resolve button on the card titled `title`. */
  resolveButton(title: string): Locator {
    return this.card(title).getByRole("button", { name: "Resolve" });
  }

  /** Presses or releases one status toggle (Open, Acknowledged, Resolved). */
  async toggleStatus(label: "Open" | "Acknowledged" | "Resolved"): Promise<void> {
    await this.statusFilter.getByRole("button", { name: label }).click();
  }
}
