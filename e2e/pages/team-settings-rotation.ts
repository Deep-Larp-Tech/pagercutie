import type { Locator, Page } from "@playwright/test";
import { TeamSettingsPage } from "./team-settings";

/** `/teams/$team/settings/rotation`: who is on call, the weekly rotation and its next shifts. */
export class TeamSettingsRotationPage extends TeamSettingsPage {
  readonly onCallNow: Locator;
  readonly order: Locator;
  readonly addToRotation: Locator;
  readonly handoffTime: Locator;
  readonly saveButton: Locator;
  readonly preview: Locator;

  constructor(page: Page) {
    super(page);
    this.onCallNow = page.getByTestId("on-call-now");
    this.order = page.getByRole("list", { name: "Rotation order" });
    this.addToRotation = page.getByRole("combobox", { name: "Add to rotation" });
    this.handoffTime = page.getByLabel("Handoff time");
    this.saveButton = page.getByRole("button", { name: "Save rotation" });
    this.preview = page.getByRole("list", { name: /^Next four shifts/ });
  }

  /** Adds `displayName` to the end of the rotation. */
  async add(displayName: string): Promise<void> {
    await this.addToRotation.click();
    await this.page.getByRole("option", { name: displayName, exact: true }).click();
  }

  /** Moves `displayName` one place up with the keyboard-reachable button. */
  async moveUp(displayName: string): Promise<void> {
    await this.page.getByRole("button", { name: `Move ${displayName} up` }).click();
  }
}
