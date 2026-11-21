import { randomUUID } from "node:crypto";
import { getAlert, getGetAlertUrl } from "../../../frontend/src/api/generated/alerts/alerts";
import { PIPELINE_TIMEOUT, createAlertingSource, waitForAlert } from "../../fixtures/alerts";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { AlertDetailPage } from "../../pages/alert-detail";
import { AlertFeed } from "../../pages/alert-feed";

test.describe("GET /api/alerts/{id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getGetAlertUrl(MISSING_ID));
  });

  test("a member opens an alert from the feed and sees its detail", async ({ asMember: { page, team }, adminApi }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const feed = new AlertFeed(page);
      await feed.goto(team.slug);

      await feed.card(title).getByRole("link", { name: title }).click({ timeout: PIPELINE_TIMEOUT });

      const detail = new AlertDetailPage(page);
      await expect(detail.title(title)).toBeVisible();
      await expect(page).toHaveURL(/\/alerts\/[0-9a-f-]+$/);
      await expect(page.getByRole("button", { name: "Acknowledge" })).toBeVisible();
    } finally {
      await source.cleanup();
    }
  });

  test("a user outside the team gets the 404 page and the API answers 404", async ({
    asUser: { page, api },
    adminApi,
    asMember: { team },
  }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const alert = await waitForAlert(adminApi, team, title);
      const detail = new AlertDetailPage(page);

      await detail.goto(alert.id);

      await expect(detail.notFound).toBeVisible();
      expect((await api.call(getAlert, alert.id)).status).toBe(404);
    } finally {
      await source.cleanup();
    }
  });
});
