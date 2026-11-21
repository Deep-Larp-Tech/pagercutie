import type { Locator, Page } from "@playwright/test";

/** The sign-in screen at `/login`. */
export class LoginPage {
  readonly email: Locator;
  readonly signInButton: Locator;

  constructor(readonly page: Page) {
    this.email = page.getByLabel("Work email");
    this.signInButton = page.getByRole("button", { name: "Sign in" });
  }

  /** Opens `/login`, with `?redirect=` when `redirect` is given. */
  async goto(redirect?: string): Promise<void> {
    await this.page.goto(redirect === undefined ? "/login" : `/login?redirect=${encodeURIComponent(redirect)}`);
  }

  /** Types `email` and submits the form. */
  async signIn(email: string): Promise<void> {
    await this.email.fill(email);
    await this.signInButton.click();
  }
}
