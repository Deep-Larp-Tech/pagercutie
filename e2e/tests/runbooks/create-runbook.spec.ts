import { createRunbook, getCreateRunbookUrl } from "../../../frontend/src/api/generated/runbooks/runbooks";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { RunbookEditorPage } from "../../pages/runbooks";
import { createTestRunbook, deleteTestRunbook, markdownRunbook, settlementRunbook } from "../../fixtures/runbooks";

test.describe("POST /api/runbooks", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "post", getCreateRunbookUrl(), {
      team_id: MISSING_ID,
      slug: "e2e-probe",
      title: "Probe",
      format: "text",
      original: "Probe",
    });
  });

  test("a member saves the YAML sample and lands on its page", async ({ asMember: { page, team } }) => {
    const editor = new RunbookEditorPage(page);
    await editor.gotoNew(team.slug);

    await editor.insertExample("YAML: settlement timeout");
    await expect(editor.title).toHaveValue("Settlement timeout");
    await editor.slug.fill(`settlement-timeout-${team.slug.slice(4, 12)}`);
    const response = await editor.create();

    expect(response.status()).toBe(201);
    const runbook = await RunbookEditorPage.createdRunbook(response);
    await expect(page).toHaveURL(`/teams/${team.slug}/runbooks/${runbook.id}`);
    expect(runbook.steps.map((step) => step.action)).toEqual(["http_get", "retry_workflow", "escalate"]);
    await expect(editor.parsedSteps).toHaveCount(3);
  });

  test("the settlement runbook's guard and matches are stored structured", async ({
    asMember: { api, team },
    adminApi,
  }) => {
    const runbook = await createTestRunbook(api, settlementRunbook(team));
    try {
      expect(runbook.attach).toEqual({
        op: "and",
        args: [
          { op: "eq", field: "payload.type", value: "WORKFLOW_FAILED" },
          { op: "eq", field: "payload.error.code", value: "TIMEOUT" },
        ],
      });
      expect(runbook.steps[2].if).toEqual({ step: 1, failures_gte: 2 });
    } finally {
      await deleteTestRunbook(adminApi, runbook);
    }
  });

  test("a structured runbook that is not valid YAML answers 422", async ({ asMember: { api, team } }) => {
    const response = await api.call(createRunbook, { ...settlementRunbook(team), original: "steps: [" });

    expect(response.status).toBe(422);
  });

  test("a viewer gets no form and the API answers 403", async ({ asViewer: { page, api, team } }) => {
    const editor = new RunbookEditorPage(page);
    await editor.gotoNew(team.slug);

    await expect(editor.readOnlyNotice).toBeVisible();
    await expect(editor.text).toHaveCount(0);

    const response = await api.call(createRunbook, markdownRunbook(team));
    expect(response.status).toBe(403);
  });
});
