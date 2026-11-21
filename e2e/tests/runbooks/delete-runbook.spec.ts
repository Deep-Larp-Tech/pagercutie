import {
  deleteRunbook,
  getDeleteRunbookUrl,
  getRunbook,
} from "../../../frontend/src/api/generated/runbooks/runbooks";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { createTestRunbook, deleteTestRunbook, settlementRunbook } from "../../fixtures/runbooks";

test.describe("DELETE /api/runbooks/{runbook_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "delete", getDeleteRunbookUrl(MISSING_ID));
  });

  test("a member deletes a runbook and its slug can be used again", async ({ asMember: { api, team }, adminApi }) => {
    const body = settlementRunbook(team);
    const runbook = await createTestRunbook(api, body);

    expect((await api.call(deleteRunbook, runbook.id)).status).toBe(204);

    expect((await api.call(getRunbook, runbook.id)).status).toBe(404);
    const again = await createTestRunbook(api, body);
    await deleteTestRunbook(adminApi, again);
  });

  test("a viewer gets 403", async ({ asViewer: { api, team }, adminApi }) => {
    const runbook = await createTestRunbook(adminApi, settlementRunbook(team));
    try {
      expect((await api.call(deleteRunbook, runbook.id)).status).toBe(403);
    } finally {
      await deleteTestRunbook(adminApi, runbook);
    }
  });
});
