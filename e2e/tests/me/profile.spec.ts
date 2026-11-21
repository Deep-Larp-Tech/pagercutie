import { getUpdateUserUrl, updateUser } from "../../../frontend/src/api/generated/users/users";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { AppShell } from "../../pages/app-shell";
import { ProfilePage } from "../../pages/profile-page";

test.describe("PATCH /api/users/{user_id} (own profile)", () => {
  test.beforeEach(async ({ adminApi }) => {
    // No user has MISSING_ID: an implemented route answers 404 and changes nothing.
    await requireImplemented(adminApi, "patch", getUpdateUserUrl(MISSING_ID), { display_name: "Probe" });
  });

  test("a user edits their profile and sees it after a reload", async ({ asUser: { page, user } }) => {
    const profile = new ProfilePage(page);
    const shell = new AppShell(page);
    const newName = `${user.display_name} Renamed`;
    await profile.goto();
    await expect(profile.email).toHaveValue(user.email);
    await expect(profile.saveButton).toBeDisabled();

    await profile.displayName.fill(newName);
    await profile.phone.fill("+420601234567");
    await profile.pickTimeZone("Tokyo", "Asia/Tokyo");
    await profile.saveButton.click();

    await expect(profile.savedToast).toBeVisible();
    await expect(shell.userMenu(newName)).toBeVisible();
    await page.reload();
    await expect(profile.displayName).toHaveValue(newName);
    await expect(profile.phone).toHaveValue("+420601234567");
    await expect(profile.timeZone).toHaveValue("Asia/Tokyo");
  });

  test("a phone number that is not E.164 shows an error under the field", async ({ asUser: { page } }) => {
    const profile = new ProfilePage(page);
    await profile.goto();

    await profile.phone.fill("601 234 567");
    await profile.saveButton.click();

    await expect(page.getByText(/Enter the number in international format/)).toBeVisible();
    await expect(profile.savedToast).toHaveCount(0);
  });

  test("another user's profile answers 403", async ({ asUser, asAdmin }) => {
    const response = await asUser.api.call(updateUser, asAdmin.user.id, { display_name: "Not allowed" });
    expect(response.status).toBe(403);
  });
});
