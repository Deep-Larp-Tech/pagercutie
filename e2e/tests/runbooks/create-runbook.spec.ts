import { createRunbook, getCreateRunbookUrl } from "../../../frontend/src/api/generated/runbooks/runbooks";
import { RunbookFormat } from "../../../frontend/src/api/generated/model";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { createTestRunbook, deleteTestRunbook, settlementRunbook } from "../../fixtures/runbooks";

test.describe("POST /api/runbooks", () => {
  test.beforeEach(async ({ adminApi }) => {
    // No such team: an implemented route answers 404 and writes nothing.
    await requireImplemented(adminApi, "post", getCreateRunbookUrl(), {
      slug: "e2e-probe",
      title: "Probe",
      team_id: MISSING_ID,
      format: RunbookFormat.text,
      original: "probe",
    });
  });

  test("a member saves the settlement runbook as executable steps", async ({ asMember: { api, team }, adminApi }) => {
    const body = settlementRunbook(team);
    const runbook = await createTestRunbook(api, body);
    try {
      expect(runbook.original).toBe(body.original);
      expect(runbook.attach).toEqual({
        op: "and",
        args: [
          { op: "eq", field: "payload.type", value: "WORKFLOW_FAILED" },
          { op: "eq", field: "payload.error.code", value: "TIMEOUT" },
        ],
      });
      expect(runbook.steps.map((step) => step.action)).toEqual(["http_get", "retry_workflow", "escalate"]);
      expect(runbook.steps[2].if).toEqual({ step: 1, failures_gte: 2 });
    } finally {
      await deleteTestRunbook(adminApi, runbook);
    }
  });

  test("a structured runbook that is not valid YAML answers 422", async ({ asMember: { api, team } }) => {
    const response = await api.call(createRunbook, { ...settlementRunbook(team), original: "steps: [" });

    expect(response.status).toBe(422);
  });

  test("a viewer gets 403", async ({ asViewer: { api, team } }) => {
    const response = await api.call(createRunbook, settlementRunbook(team));

    expect(response.status).toBe(403);
  });
});
