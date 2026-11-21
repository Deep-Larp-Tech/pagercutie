import {
  getGetRunbookUrl,
  getUpdateRunbookUrl,
  updateRunbook,
} from "../../../frontend/src/api/generated/runbooks/runbooks";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { RunbookEditorPage } from "../../pages/runbooks";
import { seedRunbook } from "../../fixtures/runbooks";

test.describe("GET and PATCH /api/runbooks/{runbook_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getGetRunbookUrl(MISSING_ID));
    await requireImplemented(adminApi, "patch", getUpdateRunbookUrl(MISSING_ID), { title: "Probe" });
  });

  test("a member renames a runbook and it stays renamed after a reload", async ({ asMember: { page, api, team } }) => {
    const runbook = await seedRunbook(api, team);
    const editor = new RunbookEditorPage(page);
    await editor.goto(team.slug, runbook.id);
    await expect(editor.title).toHaveValue(runbook.title);
    await expect(editor.saveButton).toBeDisabled();

    await editor.title.fill(`${runbook.title} renamed`);
    await editor.saveButton.click();

    await expect(page.getByText("Runbook saved", { exact: true })).toBeVisible();
    await page.reload();
    await expect(editor.title).toHaveValue(`${runbook.title} renamed`);
  });

  test("a viewer reads the runbook without controls and the API answers 403", async ({
    asViewer: { page, api, team },
    adminApi,
  }) => {
    const runbook = await seedRunbook(adminApi, team);
    const editor = new RunbookEditorPage(page);
    await editor.goto(team.slug, runbook.id);

    await expect(editor.readOnlyNotice).toBeVisible();
    await expect(editor.parsedSteps).toHaveCount(runbook.steps.length);
    await expect(editor.saveButton).toHaveCount(0);
    await expect(editor.deleteButton).toHaveCount(0);

    const response = await api.call(updateRunbook, runbook.id, { title: "Not allowed" });
    expect(response.status).toBe(403);
  });
});
