import { testRule } from "../../../frontend/src/api/generated/rules/rules";
import { expect, skipIfNotImplemented, test } from "../../fixtures";
import { RuleBuilderPage } from "../../pages/rules";

const condition = { op: "eq", field: "payload.environment", value: "prod" } as const;

test.describe("POST /api/rules/test", () => {
  test.beforeEach(async ({ adminApi }) => {
    await adminApi.callExpecting(testRule, 200, { condition, payload: { environment: "prod" } }).catch(skipIfNotImplemented);
  });

  test("a member tests a sample event in the builder", async ({ asMember: { page, team } }) => {
    const builder = new RuleBuilderPage(page);
    await page.goto(`/teams/${team.slug}/rules/new`);
    await builder.condition(1, "payload.environment", "prod");

    await builder.sample.fill('{"environment": "prod"}');
    await expect(builder.testResult("Matches: this event would raise an alert.")).toBeVisible();

    await builder.sample.fill('{"environment": "staging"}');
    await expect(builder.testResult("Doesn't match: this event would not raise an alert.")).toBeVisible();
  });

  test("any signed-in user can test a condition through the API", async ({ asUser: { api } }) => {
    const result = await api.callExpecting(testRule, 200, { condition, payload: { environment: "staging" } });
    expect(result.matched).toBe(false);
  });
});
