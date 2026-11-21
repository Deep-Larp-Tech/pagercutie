import { randomUUID } from "node:crypto";
import {
  createTeam,
  deleteTeam,
  getDeleteTeamUrl,
  getListTeamsUrl,
} from "../../../frontend/src/api/generated/teams/teams";
import {
  MISSING_ID,
  expect,
  ignoreNotImplemented,
  requireImplemented,
  skipIfNotImplemented,
  test,
} from "../../fixtures";
import { AdminTeamsPage } from "../../pages/admin-teams";

test.describe("DELETE /api/teams/{team_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "delete", getDeleteTeamUrl(MISSING_ID));
  });

  test("an admin deletes a team after confirming", async ({ asAdmin: { page }, adminApi }) => {
    await requireImplemented(adminApi, "get", getListTeamsUrl());
    const suffix = randomUUID().slice(0, 8);
    const team = await adminApi
      .callExpecting(createTeam, 201, { slug: `e2e-${suffix}`, name: `E2E deleted ${suffix}` })
      .catch(skipIfNotImplemented);
    const teams = new AdminTeamsPage(page);
    await teams.goto();

    await teams.delete(team.name);

    await expect(page.getByText(`${team.name} deleted`)).toBeVisible();
    await expect(teams.deleteDialog(team.name)).toBeHidden();
    await expect(teams.teamLink(team.name)).toHaveCount(0);
  });

  test("a user without the admin role gets 403", async ({ asUser, adminApi }) => {
    const suffix = randomUUID();
    const team = await adminApi
      .callExpecting(createTeam, 201, { slug: `e2e-${suffix}`, name: "E2E kept" })
      .catch(skipIfNotImplemented);
    try {
      const response = await asUser.api.call(deleteTeam, team.id);
      expect(response.status).toBe(403);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteTeam, 204, team.id));
    }
  });
});
