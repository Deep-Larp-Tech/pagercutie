import type { Locator, Page } from "@playwright/test";

/** The four team settings pages under `/teams/$team/settings`. */
export type TeamSettingsSection = "general" | "members" | "rotation" | "notifications";

/** What every team settings page shares: the sub-navigation and the read-only line for non-leads. */
export class TeamSettingsPage {
  readonly nav: Locator;
  readonly readOnlyNotice: Locator;
  readonly saveButtons: Locator;

  constructor(readonly page: Page) {
    this.nav = page.getByRole("navigation", { name: "Team settings" });
    this.readOnlyNotice = page.getByText("Only team leads can change this.");
    this.saveButtons = page.getByRole("button", { name: /^Save / });
  }

  /** Opens one settings page of the team with `slug`. */
  async goto(slug: string, section: TeamSettingsSection): Promise<void> {
    await this.page.goto(`/teams/${slug}/settings/${section}`);
  }

  /** The toast that confirms a save, e.g. "Rotation saved". */
  toast(text: string): Locator {
    return this.page.getByText(text, { exact: true });
  }
}
