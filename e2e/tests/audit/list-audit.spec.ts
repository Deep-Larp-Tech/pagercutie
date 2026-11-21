import { randomUUID } from "node:crypto";
import { getListAuditEntriesUrl, listAuditEntries } from "../../../frontend/src/api/generated/audit/audit";
import { AuditEntityType } from "../../../frontend/src/api/generated/model";
import { PIPELINE_TIMEOUT, createAlertingSource, waitForAlert } from "../../fixtures/alerts";
import { expect, requireImplemented, test } from "../../fixtures";
import { AlertDetailPage } from "../../pages/alert-detail";
import { AppShell } from "../../pages/app-shell";
import { AuditLogPage } from "../../pages/audit-log";

test.describe("GET /api/audit: alert history", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListAuditEntriesUrl());
  });

  test("the alert history shows an acknowledgement by its member", async ({
    asMember: { page, team, api },
    adminApi,
  }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const alert = await waitForAlert(api, team, title);
      const detail = new AlertDetailPage(page);
      await detail.goto(alert.id);

      await page.getByRole("button", { name: "Acknowledge" }).click({ timeout: PIPELINE_TIMEOUT });

      await expect(detail.historyEntry("You: Acknowledged the alert")).toBeVisible();
    } finally {
      await source.cleanup();
    }
  });

  test("a user outside the team gets none of the alert's entries", async ({
    asUser: { api },
    asMember: { team },
    adminApi,
  }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const alert = await waitForAlert(adminApi, team, title);

      const entries = await api.callExpecting(listAuditEntries, 200, {
        entity_type: AuditEntityType.alert,
        entity_id: alert.id,
      });
      expect(entries).toEqual([]);
    } finally {
      await source.cleanup();
    }
  });
});

test.describe("GET /api/audit: audit log page", () => {
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
    // A fresh id: the team's own id has entries now that team changes are audited.
    const entityId = randomUUID();
    const audit = new AuditLogPage(page);
    await audit.gotoTeam(team.slug);

    await audit.entityId.fill(entityId);
    await audit.entityType.fill(AuditEntityType.alert);
    await audit.applyFilters.click();

    await expect(page).toHaveURL(new RegExp(`entity_type=alert&entity_id=${entityId}`));
    await expect(page.getByRole("heading", { name: "No entries match these filters" })).toBeVisible();
  });

  test("a user who is not an admin gets the 404 page on the admin audit log", async ({ asUser: { page } }) => {
    const audit = new AuditLogPage(page);

    await audit.gotoAdmin();

    await expect(new AppShell(page).notFound).toBeVisible();
  });
});
