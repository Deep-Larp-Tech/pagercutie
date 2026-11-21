import { getListAuditEntriesUrl, listAuditEntries } from "../../../frontend/src/api/generated/audit/audit";
import { expect, requireImplemented, test } from "../../fixtures";
import { AppShell } from "../../pages/app-shell";
import { AuditLogPage } from "../../pages/audit-log";

test.describe("GET /api/audit", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListAuditEntriesUrl());
  });

  test("a viewer's team audit log shows what the API returns for the team", async ({ asViewer: { page, api, team } }) => {
    const entries = await api.callExpecting(listAuditEntries, 200, { team_id: team.id, limit: 100 });
    const audit = new AuditLogPage(page);

    await audit.gotoTeam(team.slug);

    if (entries.length === 0) {
      await expect(audit.empty).toBeVisible();
    } else {
      await expect(audit.entries).toHaveCount(entries.length);
    }
  });

  test("filtering by an entity id that has no entries shows the filtered empty state", async ({
    asViewer: { page, team },
  }) => {
    const audit = new AuditLogPage(page);
    await audit.gotoTeam(team.slug);

    await audit.entityId.fill(team.id);
    await audit.entityType.fill("no-such-type");
    await audit.applyFilters.click();

    await expect(page).toHaveURL(new RegExp(`entity_type=no-such-type&entity_id=${team.id}`));
    await expect(page.getByRole("heading", { name: "No entries match these filters" })).toBeVisible();
  });

  test("a user who is not an admin gets the 404 page on the admin audit log", async ({ asUser: { page } }) => {
    const audit = new AuditLogPage(page);

    await audit.gotoAdmin();

    await expect(new AppShell(page).notFound).toBeVisible();
  });
});
