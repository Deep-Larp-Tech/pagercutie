import type { Locator, Page } from "@playwright/test";

/** An audit log page: `/teams/<slug>/audit` for one team, `/admin/audit` for every team. */
export class AuditLogPage {
  readonly table: Locator;
  readonly entries: Locator;
  readonly empty: Locator;
  readonly entityType: Locator;
  readonly entityId: Locator;
  readonly applyFilters: Locator;

  constructor(readonly page: Page) {
    this.table = page.getByRole("table", { name: "Audit log" });
    // Every entry row has a link to its entity's history; skeleton rows and the expanded data rows have none.
    this.entries = this.table.getByRole("row").filter({ has: page.getByRole("link", { name: /^Show the history of/ }) });
    this.empty = page.getByRole("heading", { name: "Nothing recorded yet" });
    this.entityType = page.getByLabel("Entity type");
    this.entityId = page.getByLabel("Entity ID");
    this.applyFilters = page.getByRole("button", { name: "Apply filters" });
  }

  async gotoTeam(slug: string): Promise<void> {
    await this.page.goto(`/teams/${slug}/audit`);
  }

  async gotoAdmin(): Promise<void> {
    await this.page.goto("/admin/audit");
  }
}
