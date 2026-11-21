import type { Locator, Page } from "@playwright/test";

/** The `⌘K` / `Ctrl K` command menu opened from the header. */
export class CommandMenu {
  readonly trigger: Locator;
  readonly dialog: Locator;
  readonly input: Locator;

  constructor(readonly page: Page) {
    this.trigger = page.getByRole("button", { name: "Search" });
    this.dialog = page.getByRole("dialog", { name: "Search and commands" });
    this.input = this.dialog.getByRole("combobox");
  }

  /** Opens the menu with the platform's shortcut. */
  async openWithShortcut(): Promise<void> {
    await this.page.keyboard.press("ControlOrMeta+k");
  }

  /** The group headed `heading`, e.g. "Navigate". */
  group(heading: string): Locator {
    return this.dialog.getByRole("group", { name: heading });
  }

  /** An entry whose text starts with `label`. */
  option(label: string): Locator {
    const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return this.dialog.getByRole("option", { name: new RegExp(`^${escaped}`) });
  }
}
