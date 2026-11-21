import { randomUUID } from "node:crypto";
import { createTeam, deleteTeam, getListTeamsUrl } from "../../../frontend/src/api/generated/teams/teams";
import { expect, ignoreNotImplemented, requireImplemented, skipIfNotImplemented, test } from "../../fixtures";
import { AdminTeamsPage } from "../../pages/admin-teams";
import { AppShell } from "../../pages/app-shell";

test.describe("GET /api/teams", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListTeamsUrl());
  });

  test("an admin sees every team in the switcher", async ({ asAdmin: { page }, adminApi }) => {
    const suffix = randomUUID();
    const team = await adminApi
      .callExpecting(createTeam, 201, { slug: `e2e-${suffix}`, name: `E2E listed ${suffix.slice(0, 8)}` })
      .catch(skipIfNotImplemented);
    try {
      await page.goto(`/teams/${team.slug}/alerts`);
      const shell = new AppShell(page);

      await expect(shell.teamSwitcher).toHaveAccessibleName(`Team: ${team.name}. Switch team`);
      await shell.teamSwitcher.click();
      await expect(page.getByRole("menuitem", { name: team.name })).toBeVisible();
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteTeam, 204, team.id));
    }
  });

  test("a member sees only their own teams", async ({ asMember: { page, team } }) => {
    await page.goto("/");
    const shell = new AppShell(page);

    await shell.teamSwitcher.click();

    await expect(page.getByRole("menuitem")).toHaveText([new RegExp(team.name)]);
  });

  test("an admin sees every team on the Teams page", async ({ asAdmin: { page }, adminApi }) => {
    const suffix = randomUUID();
    const team = await adminApi
      .callExpecting(createTeam, 201, {
        slug: `e2e-${suffix}`,
        name: `E2E admin list ${suffix.slice(0, 8)}`,
        description: "Listed on /admin/teams",
      })
      .catch(skipIfNotImplemented);
    try {
      const teams = new AdminTeamsPage(page);
      await teams.goto();

      const row = teams.row(team.name);
      await expect(row).toContainText(team.slug);
      await expect(row).toContainText("Listed on /admin/teams");
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteTeam, 204, team.id));
    }
  });
});
