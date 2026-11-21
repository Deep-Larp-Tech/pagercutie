import { randomUUID } from "node:crypto";
import { createUser, deleteUser, getDeleteUserUrl, getListUsersUrl } from "../../../frontend/src/api/generated/users/users";
import {
  MISSING_ID,
  expect,
  ignoreNotImplemented,
  requireImplemented,
  skipIfNotImplemented,
  test,
  uniqueEmail,
} from "../../fixtures";
import { AdminUsersPage } from "../../pages/admin-users";

test.describe("DELETE /api/users/{user_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "delete", getDeleteUserUrl(MISSING_ID));
  });

  test("an admin deletes a user after confirming", async ({ asAdmin: { page }, adminApi }) => {
    await requireImplemented(adminApi, "get", getListUsersUrl());
    const name = `E2E deleted ${randomUUID().slice(0, 8)}`;
    await adminApi
      .callExpecting(createUser, 201, { email: uniqueEmail("deleted"), display_name: name })
      .catch(skipIfNotImplemented);
    const users = new AdminUsersPage(page);
    await users.goto();

    await users.delete(name);

    await expect(page.getByText(`${name} deleted`)).toBeVisible();
    await expect(users.deleteDialog(name)).toBeHidden();
    await expect(users.row(name)).toHaveCount(0);
  });

  test("a user without the admin role gets 403", async ({ asUser, adminApi }) => {
    const other = await adminApi
      .callExpecting(createUser, 201, { email: uniqueEmail("kept"), display_name: "E2E kept" })
      .catch(skipIfNotImplemented);
    try {
      const response = await asUser.api.call(deleteUser, other.id);
      expect(response.status).toBe(403);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteUser, 204, other.id));
    }
  });
});
