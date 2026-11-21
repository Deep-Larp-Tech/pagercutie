import { getListDeliveriesUrl } from "../../../frontend/src/api/generated/alerts/alerts";
import { expect, requireImplemented, test } from "../../fixtures";
import { AppShell } from "../../pages/app-shell";

test.describe("notifications drawer", () => {
  test("opens from the header, survives a reload and closes with Escape", async ({ asAdmin: { page } }) => {
    await page.goto("/");
    const shell = new AppShell(page);

    await shell.drawerToggle.click();
    await expect(shell.drawer).toBeVisible();
    await page.reload();
    await expect(shell.drawer).toBeVisible();

    await shell.drawer.getByRole("button", { name: "All", exact: true }).focus();
    await page.keyboard.press("Escape");
    await expect(shell.drawer).toBeHidden();
    await expect(shell.drawerToggle).toHaveAttribute("aria-expanded", "false");
  });
});

test.describe("GET /api/deliveries", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListDeliveriesUrl());
  });

  test("the drawer lists what the API returns, or says nothing was sent", async ({ asAdmin: { page } }) => {
    await page.goto("/");
    const shell = new AppShell(page);
    await shell.drawerToggle.click();

    await expect(
      shell.drawer.getByRole("list", { name: "Deliveries, newest first" }).or(shell.drawer.getByText("Nothing sent yet")),
    ).toBeVisible();
  });

  test("answers 401 without a session", async ({ playwright, baseURL }) => {
    const request = await playwright.request.newContext({ baseURL });
    const response = await request.get(getListDeliveriesUrl());
    expect(response.status()).toBe(401);
    await request.dispose();
  });
});
