import type { Locator, Page } from "@playwright/test";
import { AlertFeed } from "./alert-feed";

/** `/`: one on-call card per team, then the open alerts across teams. */
export class OverviewPage {
  readonly feed: AlertFeed;

  constructor(readonly page: Page) {
    this.feed = new AlertFeed(page);
  }

  async goto(): Promise<void> {
    await this.page.goto("/");
  }

  /** The on-call card of the team named `teamName`. */
  onCallCard(teamName: string): Locator {
    return this.page.getByRole("region", { name: `On call for ${teamName}` });
  }
}
