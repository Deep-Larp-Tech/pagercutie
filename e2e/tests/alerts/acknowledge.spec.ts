import { randomUUID } from "node:crypto";
import {
  acknowledgeAlert,
  getAcknowledgeAlertUrl,
  listAlerts,
} from "../../../frontend/src/api/generated/alerts/alerts";
import { createAlertingSource } from "../../fixtures/alerts";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { AlertFeed } from "../../pages/alert-feed";

const PIPELINE_TIMEOUT = 15_000;

test.describe("POST /api/alerts/{id}/acknowledge", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "post", getAcknowledgeAlertUrl(MISSING_ID), {});
  });

  test("a member acknowledges an alert in the feed", async ({ asMember: { page, team }, adminApi }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const feed = new AlertFeed(page);
      await feed.goto(team.slug);

      await feed.acknowledgeButton(title).click({ timeout: PIPELINE_TIMEOUT });

      await expect(feed.card(title).getByText("You're on it")).toBeVisible();
      await expect(feed.resolveButton(title)).toBeVisible();
      await expect(page.getByText("Alert acknowledged")).toBeVisible();
    } finally {
      await source.cleanup();
    }
  });

  test("a viewer sees no Acknowledge button and the API refuses", async ({
    asViewer: { page, team, api },
    adminApi,
  }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const feed = new AlertFeed(page);
      await feed.goto(team.slug);

      await expect(feed.card(title)).toBeVisible({ timeout: PIPELINE_TIMEOUT });
      await expect(feed.acknowledgeButton(title)).toHaveCount(0);
      const [alert] = await api.callExpecting(listAlerts, 200, { team_id: team.id });
      expect((await api.call(acknowledgeAlert, alert.id)).status).toBe(403);
    } finally {
      await source.cleanup();
    }
  });
});
