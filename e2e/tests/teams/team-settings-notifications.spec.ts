import {
  getGetTeamChannelPreferencesUrl,
  getSetTeamChannelPreferencesUrl,
  setTeamChannelPreferences,
} from "../../../frontend/src/api/generated/teams/teams";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { TeamSettingsNotificationsPage } from "../../pages/team-settings-notifications";

test.describe("team preferences: GET and PUT /api/teams/{id}/channel-preferences", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getGetTeamChannelPreferencesUrl(MISSING_ID));
    await requireImplemented(adminApi, "put", getSetTeamChannelPreferencesUrl(MISSING_ID), { rules: [] });
  });

  test("a lead saves two rules and sees them after a reload", async ({ asLead: { page, team } }) => {
    const notifications = new TeamSettingsNotificationsPage(page);
    await notifications.goto(team.slug, "notifications");

    await notifications.addRuleButton.click();
    await notifications.toggleChannel(1, "SMS");
    await notifications.toggleChannel(1, "Email");
    await notifications.rule(1).getByRole("switch").click();
    await notifications.addRuleButton.click();
    await notifications.saveButton.click();

    await expect(notifications.toast("Notification settings saved")).toBeVisible();
    await page.reload();
    await expect(notifications.summaries).toHaveText([
      "Critical and above: SMS, weekdays 08:00 to 20:00",
      "Critical and above: Email, at any time",
    ]);
    await expect(notifications.fallback).toBeVisible();
  });

  test("a member reads the rules and the API answers 403", async ({ asMember: { page, team, api } }) => {
    const notifications = new TeamSettingsNotificationsPage(page);
    await notifications.goto(team.slug, "notifications");

    await expect(notifications.fallback).toBeVisible();
    await expect(notifications.readOnlyNotice).toBeVisible();
    await expect(notifications.saveButton).toHaveCount(0);

    const response = await api.call(setTeamChannelPreferences, team.id, { rules: [] });
    expect(response.status).toBe(403);
  });
});
