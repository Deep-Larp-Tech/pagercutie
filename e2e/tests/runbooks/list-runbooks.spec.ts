import { getListRunbooksUrl, getRunbook, listRunbooks } from "../../../frontend/src/api/generated/runbooks/runbooks";
import { expect, requireImplemented, test } from "../../fixtures";
import { createTestRunbook, deleteTestRunbook, settlementRunbook } from "../../fixtures/runbooks";

test.describe("GET /api/runbooks", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListRunbooksUrl());
  });

  test("a viewer lists and reads the team's runbooks; a user outside the team does not see them", async ({
    asViewer: { api, team },
    asUser,
    adminApi,
  }) => {
    const runbook = await createTestRunbook(adminApi, settlementRunbook(team));
    try {
      const listed = await api.callExpecting(listRunbooks, 200, { team_id: team.id });
      expect(listed.map((item) => item.id)).toEqual([runbook.id]);
      expect(await api.callExpecting(getRunbook, 200, runbook.id)).toEqual(runbook);

      expect(await asUser.api.callExpecting(listRunbooks, 200, { team_id: team.id })).toEqual([]);
      expect((await asUser.api.call(getRunbook, runbook.id)).status).toBe(404);
    } finally {
      await deleteTestRunbook(adminApi, runbook);
    }
  });
});
