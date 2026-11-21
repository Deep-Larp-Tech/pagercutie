import type { Locator, Page } from "@playwright/test";
import { TeamSettingsPage } from "./team-settings";

/** `/teams/$team/settings/notifications`: the team's channel preferences. */
export class TeamSettingsNotificationsPage extends TeamSettingsPage {
  readonly addRuleButton: Locator;
  readonly saveButton: Locator;
  readonly summaries: Locator;
  readonly fallback: Locator;

  constructor(page: Page) {
    super(page);
    this.addRuleButton = page.getByRole("button", { name: "Add rule" });
    this.saveButton = page.getByRole("button", { name: "Save preferences" });
    this.summaries = page.getByTestId("rule-summary");
    this.fallback = page.getByText("Anything else: UI only");
  }

  /** The row of rule `number` (1-based). */
  rule(number: number): Locator {
    return this.page.getByRole("listitem", { name: `Rule ${number}` });
  }

  /** Presses the channel toggle `label` ("Email", "SMS", "Phone call", "UI") in rule `number`. */
  async toggleChannel(number: number, label: string): Promise<void> {
    await this.page.getByRole("group", { name: `Channels for rule ${number}` }).getByRole("button", { name: label }).click();
  }
}
