import type { Locator, Page } from "@playwright/test";
import { TeamSettingsPage } from "./team-settings";

/** `/teams/$team/settings/members`: members, their roles, and adding or removing them. */
export class TeamSettingsMembersPage extends TeamSettingsPage {
  readonly table: Locator;
  readonly personSearch: Locator;
  readonly newMemberRole: Locator;
  readonly addMemberButton: Locator;

  constructor(page: Page) {
    super(page);
    this.table = page.getByRole("table");
    this.personSearch = page.getByRole("combobox", { name: "Add a person" });
    this.newMemberRole = page.getByRole("combobox", { name: "Role", exact: true });
    this.addMemberButton = page.getByRole("button", { name: "Add member" });
  }

  /** The table row of the member named `displayName`. */
  row(displayName: string): Locator {
    return this.table.getByRole("row").filter({ hasText: displayName });
  }

  /** The role select in the row of `displayName` (leads only). */
  roleSelect(displayName: string): Locator {
    return this.page.getByRole("combobox", { name: `Role of ${displayName}` });
  }

  /** Searches for `query` in the combobox, picks `displayName`, chooses `role` and adds them. */
  async addMember(query: string, displayName: string, role: "Lead" | "Member" | "Viewer"): Promise<void> {
    await this.personSearch.fill(query);
    await this.page.getByRole("option", { name: new RegExp(displayName) }).click();
    await this.newMemberRole.click();
    await this.page.getByRole("option", { name: role, exact: true }).click();
    await this.addMemberButton.click();
  }

  /** Picks `role` in the row of `displayName`; the change saves at once. */
  async changeRole(displayName: string, role: "Lead" | "Member" | "Viewer"): Promise<void> {
    await this.roleSelect(displayName).click();
    await this.page.getByRole("option", { name: role, exact: true }).click();
  }
}
