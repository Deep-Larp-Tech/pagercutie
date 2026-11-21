import { randomUUID } from "node:crypto";
import { createTeam, deleteTeam, getListTeamsUrl } from "../../../frontend/src/api/generated/teams/teams";
import { expect, ignoreNotImplemented, requireImplemented, skipIfNotImplemented, test } from "../../fixtures";
import { AdminTeamsPage } from "../../pages/admin-teams";

test.describe("POST /api/teams", () => {
  test.beforeEach(async ({ adminApi }) => {
    // No team exists for a duplicate-slug probe; the setup calls below skip on the stub's 501 instead.
    await requireImplemented(adminApi, "get", getListTeamsUrl());
  });

  test("an admin adds a team, with the slug taken from the name, and opens it", async ({ asAdmin: { page }, adminApi }) => {
    const suffix = randomUUID().slice(0, 8);
    const teams = new AdminTeamsPage(page);
    await teams.goto();

    const response = await teams.addTeam(`E2E Team ${suffix}`);

    if (response.status() === 501) test.skip(true, "501: POST /api/teams not implemented yet");
    expect(response.status()).toBe(201);
    const team = await AdminTeamsPage.createdTeam(response);
    try {
      expect(team.slug).toBe(`e2e-team-${suffix}`);
      await expect(page.getByText(`${team.name} added`)).toBeVisible();
      await teams.teamLink(team.name).click();
      await expect(page).toHaveURL(`/teams/${team.slug}/alerts`);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteTeam, 204, team.id));
    }
  });

  test("the Add team dialog shows a duplicate slug under Slug", async ({ asAdmin: { page }, adminApi }) => {
    const suffix = randomUUID().slice(0, 8);
    const existing = await adminApi
      .callExpecting(createTeam, 201, { slug: `e2e-taken-${suffix}`, name: `E2E taken ${suffix}` })
      .catch(skipIfNotImplemented);
    try {
      const teams = new AdminTeamsPage(page);
      await teams.goto();

      const response = await teams.addTeam(`E2E taken ${suffix}`);

      expect(response.status()).toBe(409);
      await expect(teams.addDialog.getByText("Another team already uses this slug. Pick another one.")).toBeVisible();
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteTeam, 204, existing.id));
    }
  });

  test("a user without the admin role gets 403", async ({ asUser }) => {
    const suffix = randomUUID();
    const response = await asUser.api.call(createTeam, { slug: `e2e-${suffix}`, name: "Not allowed" });
    expect(response.status).toBe(403);
  });
});
