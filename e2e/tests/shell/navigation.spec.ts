import { getMe } from "../../../frontend/src/api/generated/auth/auth";
import { expect, test } from "../../fixtures";
import { AppShell } from "../../pages/app-shell";

test.describe("app shell", () => {
  test("an admin sees the Admin section and opens Users", async ({ asAdmin: { page, user } }) => {
    await page.goto("/");
    const shell = new AppShell(page);

    await expect(shell.userMenu(user.display_name)).toBeVisible();
    await expect(shell.adminSection).toBeVisible();
    await shell.nav.getByRole("link", { name: "Users" }).click();

    await expect(page).toHaveURL("/admin/users");
    await expect(shell.pageTitle).toHaveText("Users");
    await expect(shell.nav.getByRole("link", { name: "Users" })).toHaveAttribute("aria-current", "page");
  });

  test("a viewer sees the team pages, no Admin section, and 404 on admin pages", async ({ asViewer: { page, team } }) => {
    await page.goto("/");
    const shell = new AppShell(page);
    await expect(shell.teamSwitcher).toHaveAccessibleName(`Team: ${team.name}. Switch team`);
    await expect(shell.nav.getByRole("link", { name: "Settings" })).toBeVisible();
    await expect(shell.adminSection).toHaveCount(0);

    await page.goto("/admin/users");

    await expect(shell.notFound).toBeVisible();
  });

  test("the theme toggle sets data-theme and the choice survives a reload", async ({ asAdmin: { page } }) => {
    await page.goto("/");
    const shell = new AppShell(page);

    await shell.pickTheme("Dark");
    await expect.poll(() => shell.theme()).toBe("dark");
    expect(await page.evaluate(() => localStorage.getItem("theme"))).toBe("dark");

    await page.reload();

    await expect(shell.themeToggle.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
    expect(await shell.theme()).toBe("dark");

    await shell.pickTheme("Light");
    await expect.poll(() => shell.theme()).toBe("light");
  });

  test("an unknown path shows the 404 page inside the shell", async ({ asAdmin: { page } }) => {
    await page.goto("/no/such/page");
    const shell = new AppShell(page);

    await expect(shell.notFound).toBeVisible();
    await expect(shell.nav).toBeVisible();
    await page.getByRole("link", { name: "Go to overview" }).click();
    await expect(page).toHaveURL("/");
  });

  test("on a phone the sidebar opens as a sheet", async ({ asAdmin: { page }, adminApi }) => {
    const { user } = await adminApi.callExpecting(getMe, 200);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    const shell = new AppShell(page);
    await expect(shell.userMenu(user.display_name)).toBeVisible();
    await expect(shell.nav).toBeHidden();

    await shell.openNavigationButton.click();
    await expect(shell.navigationSheet).toBeVisible();
    await shell.navigationSheet.getByRole("link", { name: "Notifications" }).click();

    await expect(page).toHaveURL("/me/notifications");
    await expect(shell.navigationSheet).toBeHidden();
    await expect(shell.openNavigationButton).toBeFocused();
  });
});
