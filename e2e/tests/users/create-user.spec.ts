import { createUser, deleteUser, getCreateUserUrl } from "../../../frontend/src/api/generated/users/users";
import {
  ADMIN_EMAIL,
  expect,
  ignoreNotImplemented,
  requireImplemented,
  test,
  uniqueEmail,
  type UserCreate,
} from "../../fixtures";

test.describe("POST /api/users", () => {
  test.beforeEach(async ({ adminApi }) => {
    // The admin's own email: an implemented route answers 409 and creates nothing.
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

  test("a user without the admin role gets 403", async ({ asUser }) => {
    const response = await asUser.api.call(createUser, {
      email: uniqueEmail("forbidden"),
      display_name: "Not allowed",
    });
    expect(response.status).toBe(403);
  });
});
