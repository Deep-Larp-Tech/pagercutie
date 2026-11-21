import type { Locator, Page } from "@playwright/test";

/** The signed-in user's profile at `/me/profile`. */
export class ProfilePage {
  readonly email: Locator;
  readonly displayName: Locator;
  readonly phone: Locator;
  readonly timeZone: Locator;
  readonly saveButton: Locator;
  readonly savedToast: Locator;

  constructor(readonly page: Page) {
    this.email = page.getByLabel("Email");
    this.displayName = page.getByLabel("Display name");
    this.phone = page.getByLabel("Phone");
    this.timeZone = page.getByLabel("Time zone");
    this.saveButton = page.getByRole("button", { name: "Save profile" });
    this.savedToast = page.getByText("Profile saved");
  }

  async goto(): Promise<void> {
    await this.page.goto("/me/profile");
  }

  /** Types `search` into the time zone field and picks the option for `zone`. */
  async pickTimeZone(search: string, zone: string): Promise<void> {
    await this.timeZone.fill(search);
    await this.page.getByRole("option", { name: new RegExp(`^${zone}\\b`) }).click();
  }
}
