import { randomUUID } from "node:crypto";
import { createUser, deleteUser, getCreateUserUrl, getListUsersUrl } from "../../../frontend/src/api/generated/users/users";
import {
  ADMIN_EMAIL,
  expect,
  ignoreNotImplemented,
  requireImplemented,
  test,
  uniqueEmail,
  type UserCreate,
} from "../../fixtures";
import { AdminUsersPage } from "../../pages/admin-users";
import { AppShell } from "../../pages/app-shell";

test.describe("POST /api/users", () => {
  test.beforeEach(async ({ adminApi }) => {
    const probe = { email: ADMIN_EMAIL, display_name: "Probe" } satisfies UserCreate;
    await requireImplemented(adminApi, "post", getCreateUserUrl(), probe);
  });

  test("an admin creates a user", async ({ adminApi }) => {
    const email = uniqueEmail("created");
    const user = await adminApi.callExpecting(createUser, 201, { email, display_name: "Created by e2e" });
    try {
      expect(user.email).toBe(email);
      expect(user.role).toBe("user");
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteUser, 204, user.id));
    }
  });

  test("an admin adds a user through the Add user dialog", async ({ asAdmin: { page }, adminApi }) => {
    await requireImplemented(adminApi, "get", getListUsersUrl());
    const users = new AdminUsersPage(page);
    await users.goto();
    const email = uniqueEmail("ui-created");
    const name = `E2E added ${randomUUID().slice(0, 8)}`;

    const response = await users.addUser(email, name);

    expect(response.status()).toBe(201);
    const user = await AdminUsersPage.createdUser(response);
    try {
      await expect(page.getByText(`${name} added`)).toBeVisible();
      await expect(users.addDialog).toBeHidden();
      await expect(users.row(name)).toContainText(email);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteUser, 204, user.id));
    }
  });

  test("the Add user dialog shows a duplicate email under Email", async ({ asAdmin: { page }, adminApi }) => {
    await requireImplemented(adminApi, "get", getListUsersUrl());
    const users = new AdminUsersPage(page);
    await users.goto();

    const response = await users.addUser(ADMIN_EMAIL, "Duplicate");

    expect(response.status()).toBe(409);
    await expect(users.addDialog.getByText("A user with this email already exists. Use another email.")).toBeVisible();
  });

  test("a user without the admin role gets the 404 page and 403 from the API", async ({ asUser }) => {
    await asUser.page.goto("/admin/users");
    await expect(new AppShell(asUser.page).notFound).toBeVisible();

    const response = await asUser.api.call(createUser, {
      email: uniqueEmail("forbidden"),
      display_name: "Not allowed",
    });
    expect(response.status).toBe(403);
  });
});
