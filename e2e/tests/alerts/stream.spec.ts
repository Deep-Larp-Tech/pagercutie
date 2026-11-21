import { randomUUID } from "node:crypto";
import { getListAlertsUrl } from "../../../frontend/src/api/generated/alerts/alerts";
import { createAlertingSource } from "../../fixtures/alerts";
import { expect, requireImplemented, test } from "../../fixtures";
import { AlertFeed } from "../../pages/alert-feed";

const PIPELINE_TIMEOUT = 15_000;

test.describe("GET /api/alerts/stream", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListAlertsUrl());
  });

  test("a fired alert appears and repeats without a reload", async ({ asMember: { page, team }, adminApi }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const feed = new AlertFeed(page);
      await feed.goto(team.slug);
      await expect(feed.emptyState).toBeVisible();
      const workflowId = `wf-${randomUUID().slice(0, 8)}`;
      const title = `Settlement ${workflowId} failed`;

      await source.fire(workflowId);
      await expect(feed.card(title)).toBeVisible({ timeout: PIPELINE_TIMEOUT });

      await source.fire(workflowId);
      await expect(feed.card(title).getByLabel("2 occurrences")).toHaveText("×2", { timeout: PIPELINE_TIMEOUT });
      await expect(feed.connectionBar).toBeHidden();
    } finally {
      await source.cleanup();
    }
  });
});
