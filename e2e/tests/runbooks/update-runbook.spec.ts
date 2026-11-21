import {
  getGetRunbookUrl,
  getUpdateRunbookUrl,
  updateRunbook,
} from "../../../frontend/src/api/generated/runbooks/runbooks";
import { RunbookFormat } from "../../../frontend/src/api/generated/model";
import { MISSING_ID, expect, requireImplemented, test } from "../../fixtures";
import { RunbookEditorPage } from "../../pages/runbooks";
import { createTestRunbook, deleteTestRunbook, seedRunbook, settlementRunbook } from "../../fixtures/runbooks";

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

  test("a new format and text re-parse the steps and keep the condition", async ({
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
