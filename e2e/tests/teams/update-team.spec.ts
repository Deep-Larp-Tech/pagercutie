import { randomUUID } from "node:crypto";
import {
  createTeam,
  deleteTeam,
  getListTeamsUrl,
  getUpdateTeamUrl,
  updateTeam,
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

test.describe("PATCH /api/teams/{team_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "patch", getUpdateTeamUrl(MISSING_ID), { name: "Probe" });
  });

  test("an admin renames a team through the Edit team dialog", async ({ asAdmin: { page }, adminApi }) => {
    await requireImplemented(adminApi, "get", getListTeamsUrl());
    const suffix = randomUUID().slice(0, 8);
    const team = await adminApi
      .callExpecting(createTeam, 201, { slug: `e2e-${suffix}`, name: `E2E before ${suffix}` })
      .catch(skipIfNotImplemented);
    try {
      const teams = new AdminTeamsPage(page);
      await teams.goto();

      await teams.rename(team.name, `E2E after ${suffix}`);

      await expect(page.getByText(`Changes to E2E after ${suffix} saved`)).toBeVisible();
      await expect(teams.teamLink(`E2E after ${suffix}`)).toHaveAttribute("href", `/teams/${team.slug}/alerts`);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteTeam, 204, team.id));
    }
  });

  test("a user outside the team gets 403", async ({ asUser, adminApi }) => {
    const suffix = randomUUID();
    const team = await adminApi
      .callExpecting(createTeam, 201, { slug: `e2e-${suffix}`, name: "E2E untouched" })
      .catch(skipIfNotImplemented);
    try {
      const response = await asUser.api.call(updateTeam, team.id, { name: "Renamed" });
      expect(response.status).toBe(403);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteTeam, 204, team.id));
    }
  });
});
