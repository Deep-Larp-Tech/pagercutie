import { getMe, login, logout } from "../../../frontend/src/api/generated/auth/auth";
import { ADMIN_EMAIL, ApiClient, expect, test, uniqueEmail } from "../../fixtures";

// API-level checks; the screen is covered in login-screen.spec.ts.
test.describe("POST /api/auth/login", () => {
  test("the bootstrap admin logs in and GET /api/me returns role admin", async ({ apiBaseURL }) => {
    const { api, me } = await ApiClient.login(apiBaseURL, ADMIN_EMAIL);
    expect(me.user.email).toBe(ADMIN_EMAIL);

    const response = await api.call(getMe);
    expect(response.status).toBe(200);
    if (response.status === 200) expect(response.data.user.role).toBe("admin");
  });

  test("after POST /api/auth/logout, GET /api/me answers 401", async ({ apiBaseURL }) => {
    const { api } = await ApiClient.login(apiBaseURL, ADMIN_EMAIL);
    expect((await api.call(logout)).status).toBe(204);

    expect((await api.call(getMe)).status).toBe(401);
  });

  test("an unknown email answers 404", async ({ apiBaseURL }) => {
    const response = await ApiClient.anonymous(apiBaseURL).call(login, { email: uniqueEmail("unknown") });
    expect(response.status).toBe(404);
  });
});
