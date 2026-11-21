import type { Locator, Page, Response } from "@playwright/test";

/**
 * The team's source list at `/teams/$team/sources`, with its New source, Edit source, Create token, Rotate token and
 * Delete dialogs.
 */
export class SourcesPage {
  readonly table: Locator;
  readonly newSourceButton: Locator;
  readonly newDialog: Locator;
  readonly editDialog: Locator;
  readonly readOnlyNotice: Locator;

  constructor(readonly page: Page) {
    this.table = page.getByRole("table", { name: "Sources" });
    this.newSourceButton = page.getByRole("button", { name: "New source" });
    this.newDialog = page.getByRole("dialog", { name: "New source" });
    this.editDialog = page.getByRole("dialog", { name: "Edit source" });
    this.readOnlyNotice = page.getByText("Only members and leads can change this.");
  }

  async goto(teamSlug: string): Promise<void> {
    await this.page.goto(`/teams/${teamSlug}/sources`);
  }

  /** The table row of the source named `name`. */
  row(name: string): Locator {
    return this.table.getByRole("row").filter({ has: this.page.getByRole("cell", { name, exact: true }) });
  }

  /** The switch that turns the source on or off. */
  enabledSwitch(name: string): Locator {
    return this.page.getByRole("switch", { name: `Accept events from ${name}` });
  }

  /** Fills the New source dialog with a name (the slug follows it), submits it and resolves to the `POST` response. */
  async addSource(name: string): Promise<Response> {
    await this.newSourceButton.click();
    await this.newDialog.getByLabel("Name").fill(name);
    const response = this.page.waitForResponse(
      (candidate) => candidate.request().method() === "POST" && new URL(candidate.url()).pathname === "/api/sources",
    );
    await this.newDialog.getByRole("button", { name: "Add source" }).click();
    return response;
  }

  /** Opens the row's action menu and picks `action`. */
  async rowAction(name: string, action: "Edit source" | "Create token" | "Rotate token" | "Delete source"): Promise<void> {
    await this.page.getByRole("button", { name: `Actions for ${name}` }).click();
    await this.page.getByRole("menuitem", { name: action }).click();
  }

  /** The confirmation before rotating the token of the source named `name`. */
  rotateDialog(name: string): Locator {
    return this.page.getByRole("alertdialog", { name: `Rotate the token for ${name}?` });
  }

  /** The delete confirmation for the source named `name`. */
  deleteDialog(name: string): Locator {
    return this.page.getByRole("alertdialog", { name: `Delete ${name}?` });
  }

  /** The read-only field that shows a new token once, inside `dialog`. */
  tokenField(dialog: Locator): Locator {
    return dialog.getByLabel("Ingest token");
  }
}
