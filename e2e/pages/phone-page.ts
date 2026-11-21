import type { Locator, Page } from "@playwright/test";

/** The simulated phone at `/me/phone`: the user's SMS and phone-call deliveries (DEL-4). */
export class PhonePage {
  readonly phone: Locator;
  readonly channelFilter: Locator;
  readonly messages: Locator;
  readonly emptyState: Locator;

  constructor(readonly page: Page) {
    this.phone = page.getByRole("region", { name: "Simulated phone" });
    this.channelFilter = this.phone.getByRole("group", { name: "Channel" });
    this.messages = this.phone.getByRole("list", { name: "Messages, newest first" }).getByRole("listitem");
    this.emptyState = this.phone.getByText("SMS and calls sent to you show up here.");
  }

  async goto(): Promise<void> {
    await this.page.goto("/me/phone");
  }

  /** Picks All, SMS or Calls in the channel filter. */
  async filter(label: "All" | "SMS" | "Calls"): Promise<void> {
    await this.channelFilter.getByRole("button", { name: label }).click();
  }
}
