import { getMe } from "../../../frontend/src/api/generated/auth/auth";
import { ADMIN_EMAIL, expect, test, uniqueEmail } from "../../fixtures";
import { AppShell } from "../../pages/app-shell";
import { LoginPage } from "../../pages/login-page";

test.describe("sign in screen", () => {
  test("the admin signs in through the UI and lands on /", async ({ page, adminApi }) => {
    const { user } = await adminApi.callExpecting(getMe, 200);
    const login = new LoginPage(page);
    await login.goto();

    await login.signIn(ADMIN_EMAIL);

    await expect(page).toHaveURL("/");
    await expect(new AppShell(page).userMenu(user.display_name)).toBeVisible();
  });

  test("an unknown email stays on /login with the message", async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();

    await login.signIn(uniqueEmail("unknown"));

    await expect(page.getByText("No account with that email. Ask an admin to add you.")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("a deep link while signed out comes back after sign in", async ({ page, adminApi }) => {
    const { user } = await adminApi.callExpecting(getMe, 200);
    await page.goto("/?from=chat");
    await expect(page).toHaveURL(`/login?redirect=${encodeURIComponent("/?from=chat")}`);

    await new LoginPage(page).signIn(ADMIN_EMAIL);

    await expect(page).toHaveURL("/?from=chat");
    await expect(new AppShell(page).userMenu(user.display_name)).toBeVisible();
  });

  test("after sign out, / redirects to /login", async ({ asAdmin: { page, user } }) => {
    await page.goto("/");
    await new AppShell(page).signOut(user.display_name);
    await expect(page).toHaveURL("/login");

    await page.goto("/");

    await expect(page).toHaveURL(/\/login\?redirect=/);
    await expect(new LoginPage(page).email).toBeVisible();
  });
});
