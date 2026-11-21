import type { Locator, Page } from "@playwright/test";

/** An audit log page: `/teams/<slug>/audit` for one team, `/admin/audit` for every team. */
export class AuditLogPage {
  readonly table: Locator;
  readonly entries: Locator;
  readonly empty: Locator;
  readonly entityType: Locator;
  readonly filterById: Locator;
  readonly entityId: Locator;
  readonly applyFilter: Locator;

  constructor(readonly page: Page) {
    this.table = page.getByRole("table", { name: "Audit log" });
    this.entries = this.table.getByRole("row").filter({ has: page.getByRole("link", { name: /^Show the history of/ }) });
    this.empty = page.getByRole("heading", { name: "Nothing recorded yet" });
    this.entityType = page.getByRole("combobox", { name: "Entity type" });
    this.filterById = page.getByRole("button", { name: "Filter by ID" });
    this.entityId = page.getByLabel("Entity ID");
    this.applyFilter = page.getByRole("button", { name: "Apply filter" });
  }

  async gotoTeam(slug: string): Promise<void> {
    await this.page.goto(`/teams/${slug}/audit`);
  }

  /** Picks an option of the entity type select, e.g. "Alert". */
  async pickEntityType(label: string): Promise<void> {
    await this.entityType.click();
    await this.page.getByRole("option", { name: label, exact: true }).click();
  }

  async gotoAdmin(): Promise<void> {
    await this.page.goto("/admin/audit");
  }
}
