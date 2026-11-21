import { randomUUID } from "node:crypto";
import { getResolveAlertUrl, listAlerts, resolveAlert } from "../../../frontend/src/api/generated/alerts/alerts";
import { createAlertingSource } from "../../fixtures/alerts";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { AlertFeed } from "../../pages/alert-feed";
import { OverviewPage } from "../../pages/overview-page";

const PIPELINE_TIMEOUT = 15_000;

test.describe("POST /api/alerts/{id}/resolve", () => {
  test.beforeEach(async ({ adminApi }) => {
    // No such alert: an implemented route answers 404 and changes nothing.
    await requireImplemented(adminApi, "post", getResolveAlertUrl(MISSING_ID), {});
  });

  test("a member acknowledges, then resolves, and the alert leaves the open feed", async ({
    asMember: { page, team },
    adminApi,
  }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const overview = new OverviewPage(page);
      await overview.goto();
      await overview.feed.acknowledgeButton(title).click({ timeout: PIPELINE_TIMEOUT });

      await overview.feed.resolveButton(title).click();

      await expect(page.getByText("Alert resolved")).toBeVisible();
      await expect(overview.feed.card(title)).toBeHidden();
    } finally {
      await source.cleanup();
    }
  });

  test("a viewer sees no Resolve button and the API refuses", async ({ asViewer: { page, team, api }, adminApi }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const feed = new AlertFeed(page);
      await feed.goto(team.slug);

      await expect(feed.card(title)).toBeVisible({ timeout: PIPELINE_TIMEOUT });
      await expect(feed.resolveButton(title)).toHaveCount(0);
      const [alert] = await api.callExpecting(listAlerts, 200, { team_id: team.id });
      expect((await api.call(resolveAlert, alert.id, {})).status).toBe(403);
    } finally {
      await source.cleanup();
    }
  });
});
