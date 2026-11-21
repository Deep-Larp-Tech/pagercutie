import { getListRunbooksUrl } from "../../../frontend/src/api/generated/runbooks/runbooks";
import { expect, requireImplemented, test } from "../../fixtures";
import { RunbooksPage } from "../../pages/runbooks";
import { seedRunbook } from "../../fixtures/runbooks";

test.describe("GET /api/runbooks", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListRunbooksUrl());
  });

  test("a member sees the team's runbook with its format and step count", async ({ asMember: { page, api, team } }) => {
    const runbook = await seedRunbook(api, team);
    const runbooks = new RunbooksPage(page);

    await runbooks.goto(team.slug);

    const row = runbooks.row(runbook.title);
    await expect(row).toContainText(runbook.slug);
    await expect(row).toContainText("Markdown");
    await expect(row.getByRole("cell").nth(3)).toHaveText(String(runbook.steps.length));
    await expect(runbooks.newRunbookLink).toBeVisible();
  });

  test("a viewer reads the list without New runbook", async ({ asViewer: { page, team } }) => {
    const runbooks = new RunbooksPage(page);

    await runbooks.goto(team.slug);

    await expect(runbooks.emptyState).toBeVisible();
    await expect(runbooks.readOnlyNotice).toBeVisible();
    await expect(runbooks.newRunbookLink).toHaveCount(0);
  });
});
