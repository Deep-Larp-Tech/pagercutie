import type { Locator, Page } from "@playwright/test";

/** The signed-in shell around every screen: sidebar (or its sheet below 1024 px), header and content. */
export class AppShell {
  readonly nav: Locator;
  readonly adminSection: Locator;
  readonly teamSwitcher: Locator;
  readonly openNavigationButton: Locator;
  readonly navigationSheet: Locator;
  readonly themeToggle: Locator;
  readonly pageTitle: Locator;
  readonly notFound: Locator;
  readonly drawerToggle: Locator;
  readonly drawer: Locator;

  constructor(readonly page: Page) {
    this.nav = page.getByRole("navigation", { name: "Main" });
    this.adminSection = this.nav.getByRole("heading", { name: "Admin" });
    this.teamSwitcher = page.getByRole("button", { name: /^Team: .*\. Switch team$/ });
    this.openNavigationButton = page.getByRole("button", { name: "Open navigation" });
    this.navigationSheet = page.getByRole("dialog", { name: "Navigation" });
    this.themeToggle = page.getByRole("group", { name: "Theme" });
    this.pageTitle = page.getByRole("heading", { level: 1 });
    this.notFound = page.getByRole("alert").filter({ hasText: "Page not found" });
    this.drawerToggle = page.getByRole("button", { name: "Sent notifications" });
    this.drawer = page.getByRole("complementary", { name: "Sent notifications" });
  }

  /** The account menu button for the user named `displayName`. */
  userMenu(displayName: string): Locator {
    return this.page.getByRole("button", { name: `${displayName}, account menu` });
  }

  /** Opens the account menu and clicks Sign out. */
  async signOut(displayName: string): Promise<void> {
    await this.userMenu(displayName).click();
    await this.page.getByRole("menuitem", { name: "Sign out" }).click();
  }

  /** Picks Light, Dark or System in the header's theme toggle. */
  async pickTheme(label: "Light" | "Dark" | "System"): Promise<void> {
    await this.themeToggle.getByRole("button", { name: label }).click();
  }

  /** The resolved theme on `<html data-theme>`. */
  async theme(): Promise<string | undefined> {
    return this.page.evaluate(() => document.documentElement.dataset.theme);
  }
}
