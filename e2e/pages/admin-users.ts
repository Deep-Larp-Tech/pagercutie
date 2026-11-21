import type { Locator, Page, Response } from "@playwright/test";
import { CreateUserResponse } from "../../frontend/src/api/generated/users/users.zod";

/** The admin user list at `/admin/users`, with its Add user, Edit user and Delete user dialogs. */
export class AdminUsersPage {
  readonly table: Locator;
  readonly addUserButton: Locator;
  readonly addDialog: Locator;
  readonly editDialog: Locator;

  constructor(readonly page: Page) {
    this.table = page.getByRole("table", { name: "Users" });
    this.addUserButton = page.getByRole("button", { name: "Add user" });
    this.addDialog = page.getByRole("dialog", { name: "Add user" });
    this.editDialog = page.getByRole("dialog", { name: "Edit user" });
  }

  async goto(): Promise<void> {
    await this.page.goto("/admin/users");
  }

  /** The table row of the user named `displayName`; the signed-in admin's name cell also carries "(you)". */
  row(displayName: string): Locator {
    // A plain `name` matches substrings without case, so "admin" would also hit every "Admin" role badge.
    const escaped = displayName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const nameCell = new RegExp(`^${escaped}\\s*(\\(you\\))?$`);
    return this.table.getByRole("row").filter({ has: this.page.getByRole("cell", { name: nameCell }) });
  }

  /** The delete confirmation for the user named `displayName`. */
  deleteDialog(displayName: string): Locator {
    return this.page.getByRole("alertdialog", { name: `Delete ${displayName}?` });
  }

  /** Fills the Add user dialog and submits it; resolves to the `POST /api/users` response. */
  async addUser(email: string, displayName: string): Promise<Response> {
    await this.addUserButton.click();
    await this.addDialog.getByLabel("Email").fill(email);
    await this.addDialog.getByLabel("Name").fill(displayName);
    const response = this.page.waitForResponse(
      (candidate) => candidate.request().method() === "POST" && new URL(candidate.url()).pathname === "/api/users",
    );
    await this.addDialog.getByRole("button", { name: "Add user" }).click();
    return response;
  }

  /** The user a successful `addUser` created, checked against the contract. */
  static async createdUser(response: Response) {
    return CreateUserResponse.parse(await response.json());
  }

  /** Opens the row's action menu and picks `action` ("Edit user" or "Delete user"). */
  async rowAction(displayName: string, action: "Edit user" | "Delete user"): Promise<void> {
    await this.page.getByRole("button", { name: `Actions for ${displayName}` }).click();
    await this.page.getByRole("menuitem", { name: action }).click();
  }

  /** Renames the user named `displayName` through the Edit user dialog. */
  async rename(displayName: string, newName: string): Promise<void> {
    await this.rowAction(displayName, "Edit user");
    const name = this.editDialog.getByLabel("Name");
    await name.fill(newName);
    await this.editDialog.getByRole("button", { name: "Save changes" }).click();
  }

  /** Deletes the user named `displayName` and confirms. */
  async delete(displayName: string): Promise<void> {
    await this.rowAction(displayName, "Delete user");
    await this.deleteDialog(displayName).getByRole("button", { name: "Delete user" }).click();
  }
}
