import { expect, test } from "../../fixtures";
import { AppShell } from "../../pages/app-shell";
import { CommandMenu } from "../../pages/command-menu";

test.describe("command menu", () => {
  test("an admin opens it with the shortcut and goes to Users", async ({ asAdmin: { page, user } }) => {
    await page.goto("/");
    const shell = new AppShell(page);
    await expect(shell.userMenu(user.display_name)).toBeVisible();
    const menu = new CommandMenu(page);

    await menu.openWithShortcut();
    await expect(menu.dialog).toBeVisible();
    await expect(menu.input).toBeFocused();
    await menu.input.fill("users");
    // Clicked, not Enter: on the shared database an alert title containing "users" could take the first highlight.
    await menu.option("Users").click();

    await expect(page).toHaveURL("/admin/users");
    await expect(menu.dialog).toBeHidden();
    await expect(shell.pageTitle).toHaveText("Users");
  });

  test("Escape closes it and focus goes back to the Search button", async ({ asAdmin: { page } }) => {
    await page.goto("/");
    const menu = new CommandMenu(page);

    await menu.trigger.click();
    await expect(menu.dialog).toBeVisible();
    await page.keyboard.press("Escape");

    await expect(menu.dialog).toBeHidden();
    await expect(menu.trigger).toBeFocused();
  });

  test("a viewer gets the team pages and no admin pages", async ({ asViewer: { page, team } }) => {
    await page.goto("/");
    const menu = new CommandMenu(page);
    await expect(menu.trigger).toBeVisible();

    await menu.openWithShortcut();

    await expect(menu.option("Audit log").filter({ hasText: team.name })).toBeVisible();
    await expect(menu.option("Users")).toHaveCount(0);
  });
});
