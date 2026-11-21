import { getUpdateRunbookUrl, updateRunbook } from "../../../frontend/src/api/generated/runbooks/runbooks";
import { RunbookFormat } from "../../../frontend/src/api/generated/model";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { createTestRunbook, deleteTestRunbook, settlementRunbook } from "../../fixtures/runbooks";

test.describe("PATCH /api/runbooks/{runbook_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "patch", getUpdateRunbookUrl(MISSING_ID), { title: "Probe" });
  });

  test("a member switches a runbook to Markdown and the steps are re-parsed", async ({
    asMember: { api, team },
    adminApi,
  }) => {
    const runbook = await createTestRunbook(api, settlementRunbook(team));
    try {
      const updated = await api.callExpecting(updateRunbook, 200, runbook.id, {
        format: RunbookFormat.markdown,
        original: "- Check the dashboard\n- Roll back\n",
      });

      expect(updated.steps).toEqual([
        { action: "manual", text: "Check the dashboard", check: null, if: null, approval: null },
        { action: "manual", text: "Roll back", check: null, if: null, approval: null },
      ]);
      expect(updated.attach).toEqual(runbook.attach);
    } finally {
      await deleteTestRunbook(adminApi, runbook);
    }
  });

  test("a viewer gets 403", async ({ asViewer: { api, team }, adminApi }) => {
    const runbook = await createTestRunbook(adminApi, settlementRunbook(team));
    try {
      expect((await api.call(updateRunbook, runbook.id, { title: "Renamed" })).status).toBe(403);
    } finally {
      await deleteTestRunbook(adminApi, runbook);
    }
  });
});
