import {
  getGetTeamChannelPreferencesUrl,
  getGetTeamRotationUrl,
  getGetTeamUrl,
  getListTeamMembersUrl,
  getUpdateTeamUrl,
  updateTeam,
} from "../../../frontend/src/api/generated/teams/teams";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { AppShell } from "../../pages/app-shell";
import type { TeamSettingsSection } from "../../pages/team-settings";
import { TeamSettingsGeneralPage } from "../../pages/team-settings-general";

test.describe("team settings: GET and PATCH /api/teams/{id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getGetTeamUrl(MISSING_ID));
    await requireImplemented(adminApi, "patch", getUpdateTeamUrl(MISSING_ID), { name: "Renamed" });
  });

  test("a lead renames the team and the switcher follows", async ({ asLead: { page, team } }) => {
    const general = new TeamSettingsGeneralPage(page);
    await general.goto(team.slug, "general");
    const name = `${team.name} renamed`;

    await general.name.fill(name);
    await general.saveButton.click();

    await expect(general.toast("Team settings saved")).toBeVisible();
    await expect(new AppShell(page).teamSwitcher).toHaveAccessibleName(`Team: ${name}. Switch team`);
  });

  test("a member sees General read-only and the API answers 403", async ({ asMember: { page, team, api } }) => {
    const general = new TeamSettingsGeneralPage(page);
    await general.goto(team.slug, "general");

    await expect(page.getByText(team.name, { exact: true }).last()).toBeVisible();
    await expect(general.readOnlyNotice).toBeVisible();
    await expect(general.name).toHaveCount(0);

    const response = await api.call(updateTeam, team.id, { name: "Not allowed" });
    expect(response.status).toBe(403);
  });
});

test.describe("team settings read-only for members", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getGetTeamUrl(MISSING_ID));
    await requireImplemented(adminApi, "get", getListTeamMembersUrl(MISSING_ID));
    await requireImplemented(adminApi, "get", getGetTeamRotationUrl(MISSING_ID));
    await requireImplemented(adminApi, "get", getGetTeamChannelPreferencesUrl(MISSING_ID));
  });

  test("a member sees all four pages with the read-only line and no save buttons", async ({ asMember: { page, team } }) => {
    const general = new TeamSettingsGeneralPage(page);
    const sections: TeamSettingsSection[] = ["general", "members", "rotation", "notifications"];

    for (const section of sections) {
      await general.goto(team.slug, section);
      await expect(general.nav.getByRole("link", { name: new RegExp(section, "i") })).toHaveAttribute("aria-current", "page");
      await expect(general.readOnlyNotice).toBeVisible();
      await expect(general.saveButtons).toHaveCount(0);
    }
  });
});
