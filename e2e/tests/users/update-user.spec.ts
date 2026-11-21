import { randomUUID } from "node:crypto";
import {
  createUser,
  deleteUser,
  getListUsersUrl,
  getUpdateUserUrl,
  updateUser,
} from "../../../frontend/src/api/generated/users/users";
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

test.describe("PATCH /api/users/{user_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "patch", getUpdateUserUrl(MISSING_ID), { display_name: "Probe" });
  });

  test("an admin renames a user through the Edit user dialog", async ({ asAdmin: { page }, adminApi }) => {
    await requireImplemented(adminApi, "get", getListUsersUrl());
    const suffix = randomUUID().slice(0, 8);
    const user = await adminApi
      .callExpecting(createUser, 201, { email: uniqueEmail("edited"), display_name: `E2E before ${suffix}` })
      .catch(skipIfNotImplemented);
    try {
      const users = new AdminUsersPage(page);
      await users.goto();

      await users.rename(user.display_name, `E2E after ${suffix}`);

      await expect(page.getByText(`Changes to E2E after ${suffix} saved`)).toBeVisible();
      await expect(users.row(`E2E after ${suffix}`)).toContainText(user.email);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteUser, 204, user.id));
    }
  });

  test("a user without the admin role gets 403 for another user", async ({ asUser, adminApi }) => {
    const other = await adminApi
      .callExpecting(createUser, 201, { email: uniqueEmail("target"), display_name: "E2E target" })
      .catch(skipIfNotImplemented);
    try {
      const response = await asUser.api.call(updateUser, other.id, { display_name: "Renamed" });
      expect(response.status).toBe(403);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteUser, 204, other.id));
    }
  });
});
