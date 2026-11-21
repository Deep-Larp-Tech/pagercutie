import { randomUUID } from "node:crypto";
import {
  getListAlertDeliveriesUrl,
  getListDeliveriesUrl,
  listAlertDeliveries,
} from "../../../frontend/src/api/generated/alerts/alerts";
import type { Channel, ChannelPreferences } from "../../../frontend/src/api/generated/model";
import {
  getGetTeamOnCallUrl,
  getSetTeamChannelPreferencesUrl,
  getSetTeamRotationUrl,
  getTeamOnCall,
  setTeamChannelPreferences,
  setTeamRotation,
} from "../../../frontend/src/api/generated/teams/teams";
import { getUpdateUserUrl, updateUser } from "../../../frontend/src/api/generated/users/users";
import { PIPELINE_TIMEOUT, createAlertingSource, waitForAlert } from "../../fixtures/alerts";
import { MISSING_ID, expect, requireImplemented, skipIfNotImplemented, test } from "../../fixtures";
import { emailsTo, requireMailpit } from "../../fixtures/mailpit";
import { AppShell } from "../../pages/app-shell";

/** Waits until the alert has one `sent` delivery on each of `channels` and no other, and returns them by channel. */
async function waitForSent(
  api: Parameters<typeof waitForAlert>[0],
  alertId: string,
  channels: Channel[],
): Promise<Map<Channel, string>> {
  const sent = new Map<Channel, string>();
  await expect
    .poll(
      async () => {
        const deliveries = await api.callExpecting(listAlertDeliveries, 200, alertId);
        sent.clear();
        for (const delivery of deliveries) if (delivery.status === "sent") sent.set(delivery.channel, delivery.message);
        return [...sent.keys()].sort();
      },
      { timeout: PIPELINE_TIMEOUT },
    )
    .toEqual([...channels].sort());
  return sent;
}

test.describe("delivery pipeline", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListDeliveriesUrl());
    await requireImplemented(adminApi, "get", getListAlertDeliveriesUrl(MISSING_ID));
  });

  test("an event becomes one email in Mailpit and a delivery in the notifications drawer", async ({
    asMember: { page, team, user, api },
    adminApi,
  }) => {
    await requireMailpit();
    const source = await createAlertingSource(adminApi, team, {
      routing: { recipients: [{ type: "team", team_id: team.id }], channels: ["email"] },
    });
    try {
      const workflowId = `wf-${randomUUID().slice(0, 8)}`;
      const title = `Settlement ${workflowId} failed`;
      await source.fire(workflowId);
      const alert = await waitForAlert(api, team, title);

      const sent = await waitForSent(api, alert.id, ["email", "ui"]);

      expect(sent.get("email")).toBe(title);
      await expect
        .poll(async () => (await emailsTo(user.email)).filter((message) => message.subject === title).length, {
          timeout: PIPELINE_TIMEOUT,
        })
        .toBe(1);
      await page.goto("/");
      const shell = new AppShell(page);
      await shell.drawerToggle.click();
      await shell.drawer.getByRole("button", { name: "Email", exact: true }).click();
      await expect(shell.drawer.getByText(title)).toBeVisible();
    } finally {
      await source.cleanup();
    }
  });

  test.describe("Settlements on-call", () => {
    test.beforeEach(async ({ adminApi }) => {
      await requireImplemented(adminApi, "get", getGetTeamOnCallUrl(MISSING_ID));
      await requireImplemented(adminApi, "put", getSetTeamRotationUrl(MISSING_ID), { user_ids: [MISSING_ID] });
      await requireImplemented(adminApi, "put", getSetTeamChannelPreferencesUrl(MISSING_ID), { rules: [] });
      await requireImplemented(adminApi, "patch", getUpdateUserUrl(MISSING_ID), {});
    });

    test("a critical failure phones and texts the person on call, and shows in the app", async ({
      asMember: { page, team, user, api },
      adminApi,
    }) => {
      await adminApi.callExpecting(updateUser, 200, user.id, { phone: "+420777123456" }).catch(skipIfNotImplemented);
      await adminApi.callExpecting(setTeamRotation, 200, team.id, { user_ids: [user.id] });
      const preferences: ChannelPreferences = { rules: [{ min_severity: "critical", channels: ["phone", "sms"] }] };
      await adminApi.callExpecting(setTeamChannelPreferences, 200, team.id, preferences);
      expect((await api.callExpecting(getTeamOnCall, 200, team.id)).user?.id).toBe(user.id);
      const source = await createAlertingSource(adminApi, team, {
        routing: { recipients: [{ type: "on_call", team_id: team.id }] },
      });
      try {
        const workflowId = `wf-${randomUUID().slice(0, 8)}`;
        const title = `Settlement ${workflowId} failed`;
        await source.fire(workflowId);
        const alert = await waitForAlert(api, team, title);

        const sent = await waitForSent(api, alert.id, ["phone", "sms", "ui"]);

        expect(sent.get("sms")).toBe(title);
        expect(sent.get("phone")).toBe(title);
        await page.goto("/");
        const shell = new AppShell(page);
        await shell.drawerToggle.click();
        for (const filter of ["SMS", "Calls"]) {
          await shell.drawer.getByRole("button", { name: filter, exact: true }).click();
          await expect(shell.drawer.getByText(title)).toBeVisible();
        }
      } finally {
        await source.cleanup();
      }
    });
  });

  // Needs Mailpit stopped while the event is delivered and started again afterwards. A spec must not stop containers
  // other tests and other stacks share, so the retry path is covered by backend/tests/integration/pipeline/
  // test_dispatch.py (backoff, permanent failure, lease) and test_channels.py (SMTP 4xx and 5xx) instead.
  test.skip("a failed email is retried with backoff and sent once Mailpit is back, without a duplicate", () => {});
});
