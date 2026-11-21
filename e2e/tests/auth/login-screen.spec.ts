import { getMe } from "../../../frontend/src/api/generated/auth/auth";
import { ADMIN_EMAIL, expect, test, uniqueEmail } from "../../fixtures";
import { LoginPage } from "../../pages/login-page";

test.describe("sign in screen", () => {
  test("the admin signs in through the UI and lands on /", async ({ page, adminApi }) => {
    const { user } = await adminApi.callExpecting(getMe, 200);
    const login = new LoginPage(page);
    await login.goto();

    await login.signIn(ADMIN_EMAIL);

    await expect(page).toHaveURL("/");
    await expect(page.getByText(`Signed in as ${user.display_name} (${user.email})`)).toBeVisible();
  });

  test("an unknown email stays on /login with the message", async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();

    await login.signIn(uniqueEmail("unknown"));

    await expect(page.getByText("No account with that email. Ask an admin to add you.")).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("a deep link while signed out comes back after sign in", async ({ page }) => {
    await page.goto("/?from=chat");
    await expect(page).toHaveURL(`/login?redirect=${encodeURIComponent("/?from=chat")}`);

    await new LoginPage(page).signIn(ADMIN_EMAIL);

    await expect(page).toHaveURL("/?from=chat");
    await expect(page.getByText(/Signed in as/)).toBeVisible();
  });

  test("after sign out, / redirects to /login", async ({ asAdmin: { page } }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL("/login");

    await page.goto("/");

    await expect(page).toHaveURL(/\/login\?redirect=/);
    await expect(new LoginPage(page).email).toBeVisible();
  });
});
