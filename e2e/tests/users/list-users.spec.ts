import { randomUUID } from "node:crypto";
import { createUser, deleteUser, getListUsersUrl } from "../../../frontend/src/api/generated/users/users";
import {
  expect,
  ignoreNotImplemented,
  requireImplemented,
  skipIfNotImplemented,
  test,
  uniqueEmail,
  type UserCreate,
} from "../../fixtures";
import { AdminUsersPage } from "../../pages/admin-users";

test.describe("GET /api/users", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListUsersUrl());
  });

  test("an admin sees every user with their global role", async ({ asAdmin: { page, user: admin }, adminApi }) => {
    const name = `E2E listed ${randomUUID().slice(0, 8)}`;
    const body = { email: uniqueEmail("listed"), display_name: name, role: "admin" } satisfies UserCreate;
    const user = await adminApi
      .callExpecting(createUser, 201, body)
      .catch(skipIfNotImplemented);
    try {
      const users = new AdminUsersPage(page);
      await users.goto();

      await expect(users.row(name)).toContainText(user.email);
      await expect(users.row(name)).toContainText("Admin");
      await expect(users.row(admin.display_name)).toContainText("(you)");
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteUser, 204, user.id));
    }
  });
});
