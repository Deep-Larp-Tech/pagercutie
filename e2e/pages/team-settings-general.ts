import type { Locator, Page } from "@playwright/test";
import { TeamSettingsPage } from "./team-settings";

/** `/teams/$team/settings/general`: the team's name and description. */
export class TeamSettingsGeneralPage extends TeamSettingsPage {
  readonly name: Locator;
  readonly description: Locator;
  readonly saveButton: Locator;

  constructor(page: Page) {
    super(page);
    this.name = page.getByLabel("Name", { exact: true });
    this.description = page.getByLabel("Description", { exact: true });
    this.saveButton = page.getByRole("button", { name: "Save changes" });
  }
}
