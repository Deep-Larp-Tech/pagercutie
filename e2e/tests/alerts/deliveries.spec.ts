import { randomUUID } from "node:crypto";
import {
  getListAlertDeliveriesUrl,
  listAlertDeliveries,
} from "../../../frontend/src/api/generated/alerts/alerts";
import { createAlertingSource, waitForAlert } from "../../fixtures/alerts";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { AlertDetailPage } from "../../pages/alert-detail";

test.describe("GET /api/alerts/{id}/deliveries", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListAlertDeliveriesUrl(MISSING_ID));
  });

  test("the detail lists what the API returns, one row per recipient and channel", async ({
    asMember: { page, team, api },
    adminApi,
  }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const alert = await waitForAlert(api, team, title);
      const deliveries = await api.callExpecting(listAlertDeliveries, 200, alert.id);
      const detail = new AlertDetailPage(page);

      await detail.goto(alert.id);

      if (deliveries.length === 0) {
        await expect(page.getByRole("heading", { name: "Nobody was notified" })).toBeVisible();
      } else {
        await expect(detail.deliveries.getByRole("button", { name: "Show message" })).toHaveCount(deliveries.length);
        await detail.deliveries.getByRole("button", { name: "Show message" }).first().click();
        await expect(detail.deliveries.getByText(deliveries[0].message)).toBeVisible();
      }
    } finally {
      await source.cleanup();
    }
  });

  test("a user outside the team gets 404", async ({ asUser: { api }, asMember: { team }, adminApi }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const alert = await waitForAlert(adminApi, team, title);

      expect((await api.call(listAlertDeliveries, alert.id)).status).toBe(404);
    } finally {
      await source.cleanup();
    }
  });
});
