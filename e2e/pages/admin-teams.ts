import type { Locator, Page, Response } from "@playwright/test";
import { CreateTeamResponse } from "../../frontend/src/api/generated/teams/teams.zod";

/** The admin team list at `/admin/teams`, with its Add team, Edit team and Delete team dialogs. */
export class AdminTeamsPage {
  readonly table: Locator;
  readonly addTeamButton: Locator;
  readonly addDialog: Locator;
  readonly editDialog: Locator;

  constructor(readonly page: Page) {
    this.table = page.getByRole("table", { name: "Teams" });
    this.addTeamButton = page.getByRole("button", { name: "Add team" });
    this.addDialog = page.getByRole("dialog", { name: "Add team" });
    this.editDialog = page.getByRole("dialog", { name: "Edit team" });
  }

  async goto(): Promise<void> {
    await this.page.goto("/admin/teams");
  }

  /** The link on the team's name, which opens its alerts. */
  teamLink(name: string): Locator {
    return this.table.getByRole("link", { name, exact: true });
  }

  /** The delete confirmation for the team named `name`. */
  deleteDialog(name: string): Locator {
    return this.page.getByRole("alertdialog", { name: `Delete ${name}?` });
  }

  /** Fills the Add team dialog (the slug follows the name) and submits it; resolves to the `POST /api/teams` response. */
  async addTeam(name: string): Promise<Response> {
    await this.addTeamButton.click();
    await this.addDialog.getByLabel("Name").fill(name);
    const response = this.page.waitForResponse(
      (candidate) => candidate.request().method() === "POST" && new URL(candidate.url()).pathname === "/api/teams",
    );
    await this.addDialog.getByRole("button", { name: "Add team" }).click();
    return response;
  }

  /** The team a successful `addTeam` created, checked against the contract. */
  static async createdTeam(response: Response) {
    return CreateTeamResponse.parse(await response.json());
  }

  /** Opens the row's action menu and picks `action`. */
  async rowAction(name: string, action: "Edit team" | "Delete team"): Promise<void> {
    await this.page.getByRole("button", { name: `Actions for ${name}` }).click();
    await this.page.getByRole("menuitem", { name: action }).click();
  }

  /** Renames the team named `name` through the Edit team dialog. */
  async rename(name: string, newName: string): Promise<void> {
    await this.rowAction(name, "Edit team");
    await this.editDialog.getByLabel("Name").fill(newName);
    await this.editDialog.getByRole("button", { name: "Save changes" }).click();
  }

  /** Deletes the team named `name` and confirms. */
  async delete(name: string): Promise<void> {
    await this.rowAction(name, "Delete team");
    await this.deleteDialog(name).getByRole("button", { name: "Delete team" }).click();
  }
}
