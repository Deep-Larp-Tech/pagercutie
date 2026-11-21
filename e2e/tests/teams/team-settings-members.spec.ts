import { TeamRole } from "../../../frontend/src/api/generated/model";
import {
  getListTeamMembersUrl,
  getRemoveTeamMemberUrl,
  getSetTeamMemberUrl,
  setTeamMember,
} from "../../../frontend/src/api/generated/teams/teams";
import { getListUsersUrl } from "../../../frontend/src/api/generated/users/users";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { createUniqueUser, deleteCreatedUser } from "../../fixtures/personas";
import { TeamSettingsMembersPage } from "../../pages/team-settings-members";

test.describe("team members: GET /api/teams/{id}/members, PUT and DELETE /api/teams/{id}/members/{user_id}, GET /api/users", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListTeamMembersUrl(MISSING_ID));
    await requireImplemented(adminApi, "get", getListUsersUrl());
    await requireImplemented(adminApi, "put", getSetTeamMemberUrl(MISSING_ID, MISSING_ID), { role: TeamRole.member });
    await requireImplemented(adminApi, "delete", getRemoveTeamMemberUrl(MISSING_ID, MISSING_ID));
  });

  test("a lead adds a member through the combobox", async ({ asLead: { page, team }, adminApi }) => {
    const newcomer = await createUniqueUser(adminApi, "newcomer");
    try {
      const members = new TeamSettingsMembersPage(page);
      await members.goto(team.slug, "members");

      await members.addMember(newcomer.email, newcomer.display_name, "Member");

      await expect(members.toast(`${newcomer.display_name} added as a member`)).toBeVisible();
      await expect(members.row(newcomer.display_name)).toContainText(newcomer.email);
    } finally {
      await deleteCreatedUser(adminApi, newcomer);
    }
  });

  test("a lead changes a member's role", async ({ asLead: { page, team }, adminApi }) => {
    const colleague = await createUniqueUser(adminApi, "colleague");
    try {
      await adminApi.callExpecting(setTeamMember, 200, team.id, colleague.id, { role: TeamRole.member });
      const members = new TeamSettingsMembersPage(page);
      await members.goto(team.slug, "members");

      await members.changeRole(colleague.display_name, "Viewer");

      await expect(members.toast(`${colleague.display_name} is now a viewer`)).toBeVisible();
      await page.reload();
      await expect(members.roleSelect(colleague.display_name)).toHaveText("Viewer");
    } finally {
      await deleteCreatedUser(adminApi, colleague);
    }
  });

  test("the only lead cannot demote or remove themselves", async ({ asLead: { page, team, user } }) => {
    const members = new TeamSettingsMembersPage(page);
    await members.goto(team.slug, "members");

    await expect(members.roleSelect(user.display_name)).toHaveAttribute("data-disabled", "");
    await expect(members.row(user.display_name).getByRole("button", { name: /^Remove/ })).toBeDisabled();
  });

  test("a member sees the list without controls and the API answers 403", async ({ asMember: { page, team, user, api } }) => {
    const members = new TeamSettingsMembersPage(page);
    await members.goto(team.slug, "members");

    await expect(members.row(user.display_name)).toContainText("Member");
    await expect(members.readOnlyNotice).toBeVisible();
    await expect(members.personSearch).toHaveCount(0);
    await expect(members.table.getByRole("button")).toHaveCount(0);

    const response = await api.call(setTeamMember, team.id, user.id, { role: TeamRole.lead });
    expect(response.status).toBe(403);
  });
});
