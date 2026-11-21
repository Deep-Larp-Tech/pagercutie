import type { Locator, Page } from "@playwright/test";

/** The rule list at `/teams/$team/rules` or `/me/rules`. */
export class RulesPage {
  readonly table: Locator;
  readonly newRuleLink: Locator;
  readonly readOnlyNotice: Locator;

  constructor(readonly page: Page) {
    this.table = page.getByRole("table");
    this.newRuleLink = page.getByRole("link", { name: "New rule" }).first();
    this.readOnlyNotice = page.getByText("Only members and leads of this team can change its rules.");
  }

  /** Opens a team's rules, or the signed-in user's personal rules when `teamSlug` is `null`. */
  async goto(teamSlug: string | null): Promise<void> {
    await this.page.goto(teamSlug === null ? "/me/rules" : `/teams/${teamSlug}/rules`);
  }

  /** The table row of the rule named `name`. */
  row(name: string): Locator {
    return this.table.getByRole("row").filter({ has: this.page.getByRole("link", { name, exact: true }) });
  }

  /** The on switch of the rule named `name`. */
  enabledSwitch(name: string): Locator {
    return this.page.getByRole("switch", { name: `Rule ${name} is on` });
  }
}

/** The rule builder at `/teams/$team/rules/new`, `/teams/$team/rules/$ruleId` and their `/me/rules` twins. */
export class RuleBuilderPage {
  readonly name: Locator;
  readonly title: Locator;
  readonly sentence: Locator;
  readonly sample: Locator;
  readonly saveButton: Locator;
  readonly deleteButton: Locator;

  constructor(readonly page: Page) {
    this.name = page.getByRole("textbox", { name: "Rule name" });
    this.title = page.getByRole("textbox", { name: "Title" });
    this.sentence = page.getByTestId("condition-sentence");
    this.sample = page.getByLabel("Sample event payload (JSON)");
    this.saveButton = page.getByRole("button", { name: "Save rule" });
    this.deleteButton = page.getByRole("button", { name: "Delete rule" });
  }

  /** Fills predicate `index` (1-based, top level) with `field is value`; adds the row first when it is not there yet. */
  async condition(index: number, field: string, value: string): Promise<void> {
    if ((await this.page.getByLabel(`Field ${index}`).count()) === 0) {
      await this.page.getByRole("button", { name: "Add condition", exact: true }).click();
    }
    await this.page.getByLabel(`Field ${index}`).fill(field);
    await this.page.keyboard.press("Escape");
    await this.page.getByLabel(`Value ${index}`).fill(value);
  }

  /** The delete confirmation for the rule named `name`. */
  deleteDialog(name: string): Locator {
    return this.page.getByRole("alertdialog", { name: `Delete ${name}?` });
  }

  /** The test panel's verdict. */
  testResult(text: string): Locator {
    return this.page.getByRole("status").filter({ hasText: text });
  }
}
