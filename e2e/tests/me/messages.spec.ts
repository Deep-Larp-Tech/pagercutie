import { getListMyMessagesUrl, listMyMessages } from "../../../frontend/src/api/generated/alerts/alerts";
import type { ListMyMessagesParams } from "../../../frontend/src/api/generated/model";
import { ApiClient, expect, requireImplemented, test } from "../../fixtures";
import { PhonePage } from "../../pages/phone-page";

test.describe("GET /api/me/messages", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListMyMessagesUrl());
  });

  test("the phone page lists the messages the API returns", async ({ asAdmin: { page, api } }) => {
    // The same channels the page asks for.
    const params: ListMyMessagesParams = { channel: ["sms", "phone"] };
    const messages = await api.callExpecting(listMyMessages, 200, params);
    const phone = new PhonePage(page);

    await phone.goto();

    if (messages.length === 0) {
      await expect(phone.emptyState).toBeVisible();
    } else {
      await expect(phone.messages.first()).toContainText(messages[0].message);
    }
  });

  test("a new user's phone is empty, and the SMS filter keeps it so", async ({ asUser: { page } }) => {
    const phone = new PhonePage(page);
    await phone.goto();

    await expect(phone.emptyState).toBeVisible();
    await phone.filter("SMS");
    await expect(page).toHaveURL("/me/phone?channel=sms");
    await expect(phone.emptyState).toBeVisible();
  });

  test("without a session the API answers 401", async ({ apiBaseURL }) => {
    const response = await ApiClient.anonymous(apiBaseURL).call(listMyMessages, undefined);
    expect(response.status).toBe(401);
  });
});
