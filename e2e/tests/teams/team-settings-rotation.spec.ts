import { TeamRole } from "../../../frontend/src/api/generated/model";
import {
  getGetTeamOnCallUrl,
  getGetTeamRotationUrl,
  getSetTeamRotationUrl,
  setTeamMember,
  setTeamRotation,
} from "../../../frontend/src/api/generated/teams/teams";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { createUniqueUser, deleteCreatedUser } from "../../fixtures/personas";
import { TeamSettingsRotationPage } from "../../pages/team-settings-rotation";

test.describe("rotation: GET and PUT /api/teams/{id}/rotation, GET /api/teams/{id}/on-call", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getGetTeamRotationUrl(MISSING_ID));
    await requireImplemented(adminApi, "get", getGetTeamOnCallUrl(MISSING_ID));
    await requireImplemented(adminApi, "put", getSetTeamRotationUrl(MISSING_ID), { user_ids: [MISSING_ID] });
  });

  test("a lead reorders the rotation and the order survives a reload", async ({ asLead: { page, team, user }, adminApi }) => {
    const colleague = await createUniqueUser(adminApi, "oncall");
    try {
      await adminApi.callExpecting(setTeamMember, 200, team.id, colleague.id, { role: TeamRole.member });
      await adminApi.callExpecting(setTeamRotation, 200, team.id, { user_ids: [user.id, colleague.id] });
      const rotation = new TeamSettingsRotationPage(page);
      await rotation.goto(team.slug, "rotation");
      await expect(rotation.onCallNow).toContainText(`You are on call`);

      await rotation.moveUp(colleague.display_name);
      await expect(rotation.preview.getByRole("listitem").first()).toContainText(colleague.display_name);
      await rotation.saveButton.click();

      await expect(rotation.toast("Rotation saved")).toBeVisible();
      await page.reload();
      await expect(rotation.order.getByRole("listitem")).toHaveText([
        new RegExp(colleague.display_name),
        new RegExp(user.display_name),
      ]);
      await expect(rotation.onCallNow).toContainText(`${colleague.display_name} is on call`);
    } finally {
      await deleteCreatedUser(adminApi, colleague);
    }
  });

  test("a member sees the rotation read-only and the API answers 403", async ({ asMember: { page, team, user, api }, adminApi }) => {
    await adminApi.callExpecting(setTeamRotation, 200, team.id, { user_ids: [user.id] });
    const rotation = new TeamSettingsRotationPage(page);
    await rotation.goto(team.slug, "rotation");

    await expect(rotation.order.getByRole("listitem")).toHaveText([user.display_name]);
    await expect(rotation.readOnlyNotice).toBeVisible();
    await expect(rotation.saveButton).toHaveCount(0);

    const response = await api.call(setTeamRotation, team.id, { user_ids: [user.id] });
    expect(response.status).toBe(403);
  });
});
