import type { Locator, Page, Response } from "@playwright/test";
import { CreateRunbookResponse } from "../../frontend/src/api/generated/runbooks/runbooks.zod";

/** Read-only line every runbook page shows to viewers. */
const READ_ONLY = "Only members and leads can change runbooks.";

/** `/teams/$team/runbooks`: the team's runbook table and **New runbook**. */
export class RunbooksPage {
  readonly table: Locator;
  readonly newRunbookLink: Locator;
  readonly readOnlyNotice: Locator;
  readonly emptyState: Locator;

  constructor(readonly page: Page) {
    this.table = page.getByRole("table", { name: "Runbooks" });
    this.newRunbookLink = page.getByRole("link", { name: "New runbook" });
    this.readOnlyNotice = page.getByText(READ_ONLY);
    this.emptyState = page.getByText("No runbooks yet");
  }

  async goto(team: string): Promise<void> {
    await this.page.goto(`/teams/${team}/runbooks`);
  }

  /** The table row of the runbook titled `title`. */
  row(title: string): Locator {
    return this.table.getByRole("row").filter({ has: this.page.getByRole("link", { name: title, exact: true }) });
  }
}

/** The runbook editor at `/teams/$team/runbooks/new` and `/teams/$team/runbooks/$runbookId`, with its preview. */
export class RunbookEditorPage {
  readonly title: Locator;
  readonly slug: Locator;
  readonly text: Locator;
  readonly formats: Locator;
  readonly insertExampleButton: Locator;
  readonly saveButton: Locator;
  readonly deleteButton: Locator;
  readonly parsedSteps: Locator;
  readonly readOnlyNotice: Locator;

  constructor(readonly page: Page) {
    this.title = page.getByLabel("Title", { exact: true });
    this.slug = page.getByLabel("Slug", { exact: true });
    this.text = page.getByLabel("Runbook text", { exact: true });
    this.formats = page.getByRole("group", { name: "Format" });
    this.insertExampleButton = page.getByRole("button", { name: "Insert example" });
    this.saveButton = page.getByRole("button", { name: "Save runbook" });
    this.deleteButton = page.getByRole("button", { name: "Delete runbook" });
    this.parsedSteps = page.getByRole("list", { name: "Parsed steps" }).getByRole("listitem");
    this.readOnlyNotice = page.getByText(READ_ONLY);
  }

  async gotoNew(team: string): Promise<void> {
    await this.page.goto(`/teams/${team}/runbooks/new`);
  }

  async goto(team: string, runbookId: string): Promise<void> {
    await this.page.goto(`/teams/${team}/runbooks/${runbookId}`);
  }

  /** Picks a format: "YAML", "Markdown", "Free text" or "Link". */
  async pickFormat(label: "YAML" | "Markdown" | "Free text" | "Link"): Promise<void> {
    await this.formats.getByRole("button", { name: label }).click();
  }

  /** Inserts a §6.2 sample, e.g. "YAML: settlement timeout". */
  async insertExample(label: string): Promise<void> {
    await this.insertExampleButton.click();
    await this.page.getByRole("menuitem", { name: label }).click();
  }

  /** Clicks **Save runbook**; resolves to the `POST /api/runbooks` response. */
  async create(): Promise<Response> {
    const response = this.page.waitForResponse(
      (candidate) => candidate.request().method() === "POST" && new URL(candidate.url()).pathname === "/api/runbooks",
    );
    await this.saveButton.click();
    return response;
  }

  /** The runbook a successful `create` saved, checked against the contract. */
  static async createdRunbook(response: Response) {
    return CreateRunbookResponse.parse(await response.json());
  }

  /** Deletes the open runbook and confirms. */
  async delete(title: string): Promise<void> {
    await this.deleteButton.click();
    await this.page
      .getByRole("alertdialog", { name: `Delete ${title}?` })
      .getByRole("button", { name: "Delete runbook" })
      .click();
  }
}
