import type { RuleCreate, TeamRead } from "../../../frontend/src/api/generated/model";
import {
  createRule,
  deleteRule,
  getCreateRuleUrl,
  getDeleteRuleUrl,
  getGetRuleUrl,
  getListRulesUrl,
  getUpdateRuleUrl,
  listRules,
  updateRule,
} from "../../../frontend/src/api/generated/rules/rules";
import { MISSING_ID, expect, ignoreNotImplemented, requireImplemented, skipIfNotImplemented, test, type ApiClient } from "../../fixtures";
import { RuleBuilderPage, RulesPage } from "../../pages/rules";

/** A rule body owned by `team`, like Team Settlements' (SPEC §4.3). */
function settlementRule(team: TeamRead, name: string): RuleCreate {
  return {
    name,
    owner: { type: "team", team_id: team.id },
    condition: {
      op: "and",
      args: [
        { op: "eq", field: "payload.type", value: "WORKFLOW_FAILED" },
        { op: "eq", field: "payload.environment", value: "prod" },
      ],
    },
    routing: { recipients: [{ type: "on_call", team_id: team.id }], channels: ["phone", "sms"] },
    presentation: { title: "Settlement {{payload.workflowId}} failed", severity: "critical", colour: "red" },
  };
}

async function seedRule(api: ApiClient, team: TeamRead, name: string) {
  return api.callExpecting(createRule, 201, settlementRule(team, name)).catch(skipIfNotImplemented);
}

test.describe("GET /api/rules", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListRulesUrl());
  });

  test("a member sees the team's rules", async ({ asMember: { page, team, api } }) => {
    const rule = await seedRule(api, team, "E2E listed rule");
    try {
      const rules = new RulesPage(page);
      await rules.goto(team.slug);

      await expect(rules.row(rule.name)).toContainText("Critical");
      await expect(rules.row(rule.name)).toContainText(`On call in ${team.name}`);
    } finally {
      await ignoreNotImplemented(() => api.callExpecting(deleteRule, 204, rule.id));
    }
  });

  test("a viewer reads the list without switches or New rule", async ({ asViewer: { page, team } }) => {
    const rules = new RulesPage(page);
    await rules.goto(team.slug);

    await expect(rules.readOnlyNotice).toBeVisible();
    await expect(page.getByRole("switch")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "New rule" })).toHaveCount(0);
  });

  test("another team's rules stay hidden from a user outside it", async ({ asMember: { team, api }, asUser }) => {
    const rule = await seedRule(api, team, "E2E hidden rule");
    try {
      // DOMAIN.md §4 allows either answer: refused, or a list without the team's rules.
      const response = await asUser.api.call(listRules, { team_id: team.id });
      if (response.status === 200) expect(response.data.map(({ id }) => id)).not.toContain(rule.id);
      else expect(response.status).toBe(403);
    } finally {
      await ignoreNotImplemented(() => api.callExpecting(deleteRule, 204, rule.id));
    }
  });
});

test.describe("POST /api/rules", () => {
  test.beforeEach(async ({ adminApi }) => {
    // A missing team owner answers 404 on an implemented route and writes nothing.
    await requireImplemented(adminApi, "post", getCreateRuleUrl(), settlementRule({ id: MISSING_ID, slug: "x", name: "x", description: null, created_at: "" }, "probe"));
  });

  test("a member builds Team Settlements' rule and it shows in the list", async ({ asMember: { page, team } }) => {
    const builder = new RuleBuilderPage(page);
    await page.goto(`/teams/${team.slug}/rules/new`);
    const name = `E2E settlement ${Date.now()}`;

    await builder.name.fill(name);
    await builder.condition(1, "payload.type", "WORKFLOW_FAILED");
    await builder.condition(2, "payload.workflowName", "order-settlement");
    await builder.condition(3, "payload.environment", "prod");
    await expect(builder.sentence).toHaveText("type is WORKFLOW_FAILED and workflowName is order-settlement and environment is prod");
    await builder.title.fill("Settlement {{payload.workflowId}} failed at {{payload.step}}");
    await builder.saveButton.click();

    await expect(page.getByText("Rule saved")).toBeVisible();
    await expect(new RulesPage(page).row(name)).toBeVisible();
  });

  test("a viewer cannot add a rule and the API answers 403", async ({ asViewer: { page, team, api } }) => {
    await page.goto(`/teams/${team.slug}/rules/new`);
    await expect(page.getByText("You can't add rules here")).toBeVisible();

    const response = await api.call(createRule, settlementRule(team, "Not allowed"));
    expect(response.status).toBe(403);
  });
});

test.describe("GET, PATCH and DELETE /api/rules/{id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getGetRuleUrl(MISSING_ID));
    await requireImplemented(adminApi, "patch", getUpdateRuleUrl(MISSING_ID), { name: "Renamed" });
    await requireImplemented(adminApi, "delete", getDeleteRuleUrl(MISSING_ID));
  });

  test("a member switches a rule off, renames it, then deletes it", async ({ asMember: { page, team, api } }) => {
    const rule = await seedRule(api, team, `E2E edited ${Date.now()}`);
    const rules = new RulesPage(page);
    await rules.goto(team.slug);

    await rules.enabledSwitch(rule.name).click();
    await expect(rules.enabledSwitch(rule.name)).not.toBeChecked();

    await rules.row(rule.name).getByRole("link").click();
    const builder = new RuleBuilderPage(page);
    const renamed = `${rule.name} renamed`;
    await builder.name.fill(renamed);
    await builder.saveButton.click();
    await expect(page.getByText("Rule saved")).toBeVisible();

    await builder.deleteButton.click();
    await builder.deleteDialog(renamed).getByRole("button", { name: "Delete rule" }).click();
    await expect(page.getByText("Rule deleted")).toBeVisible();
    await expect(rules.row(renamed)).toHaveCount(0);
  });

  test("a viewer sees a rule read-only and the API refuses changes", async ({ asViewer: { page, team, api }, adminApi }) => {
    const rule = await seedRule(adminApi, team, `E2E read-only ${Date.now()}`);
    try {
      await page.goto(`/teams/${team.slug}/rules/${rule.id}`);
      await expect(new RuleBuilderPage(page).name).toBeDisabled();
      await expect(page.getByRole("button", { name: "Save rule" })).toHaveCount(0);

      expect((await api.call(updateRule, rule.id, { enabled: false })).status).toBe(403);
      expect((await api.call(deleteRule, rule.id)).status).toBe(403);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteRule, 204, rule.id));
    }
  });
});
