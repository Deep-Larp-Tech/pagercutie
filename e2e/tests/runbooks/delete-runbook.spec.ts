import {
  deleteRunbook,
  getDeleteRunbookUrl,
  getRunbook,
} from "../../../frontend/src/api/generated/runbooks/runbooks";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { RunbookEditorPage, RunbooksPage } from "../../pages/runbooks";
import { seedRunbook } from "../../fixtures/runbooks";

test.describe("DELETE /api/runbooks/{runbook_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "delete", getDeleteRunbookUrl(MISSING_ID));
  });

  test("a member deletes a runbook after confirming", async ({ asMember: { page, api, team } }) => {
    const runbook = await seedRunbook(api, team);
    const editor = new RunbookEditorPage(page);
    await editor.goto(team.slug, runbook.id);

    await editor.delete(runbook.title);

    await expect(page).toHaveURL(`/teams/${team.slug}/runbooks`);
    await expect(new RunbooksPage(page).emptyState).toBeVisible();
    expect((await api.call(getRunbook, runbook.id)).status).toBe(404);
  });

  test("a viewer gets 403 from the API", async ({ asViewer: { api, team }, adminApi }) => {
    const runbook = await seedRunbook(adminApi, team);

    const response = await api.call(deleteRunbook, runbook.id);

    expect(response.status).toBe(403);
  });
});
