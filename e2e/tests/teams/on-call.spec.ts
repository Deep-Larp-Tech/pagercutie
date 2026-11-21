import {
  getGetTeamOnCallUrl,
  getSetTeamRotationUrl,
  setTeamRotation,
} from "../../../frontend/src/api/generated/teams/teams";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { OverviewPage } from "../../pages/overview-page";

test.describe("GET /api/teams/{id}/on-call", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getGetTeamOnCallUrl(MISSING_ID));
  });

  test("a team without a rotation says so", async ({ asMember: { page, team } }) => {
    const overview = new OverviewPage(page);
    await overview.goto();

    await expect(overview.onCallCard(team.name)).toContainText("No rotation set");
  });

  test("the rotation set in setup shows the lead on call", async ({ asLead: { page, team, user, api }, adminApi }) => {
    await requireImplemented(adminApi, "put", getSetTeamRotationUrl(MISSING_ID), { user_ids: [MISSING_ID] });
    await api.callExpecting(setTeamRotation, 200, team.id, { user_ids: [user.id] });
    const overview = new OverviewPage(page);

    await overview.goto();

    await expect(overview.onCallCard(team.name)).toContainText(/^.*You're on call until \w{3} \d{2}:\d{2}$/);
  });

  test("a member cannot set the rotation", async ({ asMember: { team, user, api }, adminApi }) => {
    await requireImplemented(adminApi, "put", getSetTeamRotationUrl(MISSING_ID), { user_ids: [MISSING_ID] });

    const response = await api.call(setTeamRotation, team.id, { user_ids: [user.id] });

    expect(response.status).toBe(403);
  });
});
