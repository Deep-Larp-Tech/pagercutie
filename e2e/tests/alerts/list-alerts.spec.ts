import { randomUUID } from "node:crypto";
import { acknowledgeAlert, getListAlertsUrl, listAlerts } from "../../../frontend/src/api/generated/alerts/alerts";
import { createAlertingSource } from "../../fixtures/alerts";
import { expect, requireImplemented, test } from "../../fixtures";
import { AlertFeed } from "../../pages/alert-feed";

/** How long the pipeline may take from ingest to a card in the feed. */
const PIPELINE_TIMEOUT = 15_000;

test.describe("GET /api/alerts", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListAlertsUrl());
  });

  test("a member sees the empty team feed and its link to the rules", async ({ asMember: { page, team } }) => {
    const feed = new AlertFeed(page);
    await feed.goto(team.slug);

    await expect(feed.emptyState).toHaveText("No open alerts");
    await expect(page.getByRole("link", { name: "Open rules" })).toHaveAttribute("href", `/teams/${team.slug}/rules`);
  });

  test("a member filters the team feed by status", async ({ asMember: { page, team, api }, adminApi }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const open = `wf-${randomUUID().slice(0, 8)}`;
      const acknowledged = `wf-${randomUUID().slice(0, 8)}`;
      await source.fire(open);
      await source.fire(acknowledged);
      const feed = new AlertFeed(page);
      await feed.goto(team.slug);
      await expect(feed.card(`Settlement ${acknowledged} failed`)).toBeVisible({ timeout: PIPELINE_TIMEOUT });
      const listed = await api.callExpecting(listAlerts, 200, { team_id: team.id });
      const target = listed.find((alert) => alert.title === `Settlement ${acknowledged} failed`);
      if (target === undefined) throw new Error("The fired alert is not in GET /alerts");
      await api.callExpecting(acknowledgeAlert, 200, target.id);

      await feed.toggleStatus("Open");

      await expect(page).toHaveURL(/status=/);
      await expect(feed.card(`Settlement ${acknowledged} failed`)).toBeVisible();
      await expect(feed.card(`Settlement ${open} failed`)).toBeHidden();
    } finally {
      await source.cleanup();
    }
  });

  test("a user outside the team does not get the team's alerts", async ({ asMember: { team }, asUser, adminApi }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      await source.fire(`wf-${randomUUID().slice(0, 8)}`);
      await expect
        .poll(async () => (await adminApi.callExpecting(listAlerts, 200, { team_id: team.id })).length, {
          timeout: PIPELINE_TIMEOUT,
        })
        .toBeGreaterThan(0);

      // GET /alerts lists only what the caller can see (DOMAIN.md §4), so another team's alerts are left out.
      const visible = await asUser.api.callExpecting(listAlerts, 200, { team_id: team.id });

      expect(visible).toEqual([]);
    } finally {
      await source.cleanup();
    }
  });
});
