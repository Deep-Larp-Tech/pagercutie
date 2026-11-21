import { randomUUID } from "node:crypto";
import { getListAuditEntriesUrl, listAuditEntries } from "../../../frontend/src/api/generated/audit/audit";
import { PIPELINE_TIMEOUT, createAlertingSource, waitForAlert } from "../../fixtures/alerts";
import { expect, requireImplemented, test } from "../../fixtures";
import { AlertDetailPage } from "../../pages/alert-detail";

test.describe("GET /api/audit", () => {
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

      const entries = await api.callExpecting(listAuditEntries, 200, { entity_type: "alert", entity_id: alert.id });
      expect(entries).toEqual([]);
    } finally {
      await source.cleanup();
    }
  });
});
