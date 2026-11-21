import { randomUUID } from "node:crypto";
import {
  decideStep,
  getDecideStepUrl,
  getGetRunbookRunUrl,
  getRunbookRun,
} from "../../../frontend/src/api/generated/alerts/alerts";
import { PIPELINE_TIMEOUT, createAlertingSource, waitForAlert } from "../../fixtures/alerts";
import type { MembershipSet, StepDecision } from "../../../frontend/src/api/generated/model";
import { setTeamMember } from "../../../frontend/src/api/generated/teams/teams";
import { MISSING_ID, expect, requireImplemented, skipIfNotImplemented, test } from "../../fixtures";
import { AlertDetailPage } from "../../pages/alert-detail";

/** One step a lead must approve before it runs (`RUN-4`). */
const APPROVAL_RUNBOOK = `steps:
  - action: restart_service
    service: "settlement-{{workflowId}}"
    approval: required
`;

/** One manual step a member ticks off. */
const MANUAL_RUNBOOK = `steps:
  - action: manual
    text: "Call the counterparty about {{workflowId}}"
`;

const approve: StepDecision = { decision: "approve" };
const done: StepDecision = { decision: "done" };
const viewer: MembershipSet = { role: "viewer" };

test.describe("GET /api/alerts/{id}/runbook-run", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getGetRunbookRunUrl(MISSING_ID));
  });

  test("an alert without a runbook says so", async ({ asMember: { page, team, api }, adminApi }) => {
    const source = await createAlertingSource(adminApi, team);
    try {
      const title = `Settlement wf-${randomUUID().slice(0, 8)} failed`;
      await source.fire(title.split(" ")[1]);
      const alert = await waitForAlert(api, team, title);
      const detail = new AlertDetailPage(page);

      await detail.goto(alert.id);

      await expect(detail.noRunbook).toBeVisible();
    } finally {
      await source.cleanup();
    }
  });

  test("the steps show with their parameters filled from the event", async ({
    asMember: { page, team, api },
    adminApi,
  }) => {
    const source = await createAlertingSource(adminApi, team, { runbook: APPROVAL_RUNBOOK });
    try {
      const workflowId = `wf-${randomUUID().slice(0, 8)}`;
      await source.fire(workflowId);
      const alert = await waitForAlert(api, team, `Settlement ${workflowId} failed`);
      const detail = new AlertDetailPage(page);

      await detail.goto(alert.id);

      await expect(detail.step(1)).toContainText("Restart a service");
      await expect(detail.step(1)).toContainText(`settlement-${workflowId}`);
    } finally {
      await source.cleanup();
    }
  });
});

test.describe("POST /api/alerts/{id}/runbook-run/steps/{index}/decision", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "post", getDecideStepUrl(MISSING_ID, 0), { decision: "approve" });
  });

  test("a lead approves a risky step after the confirmation", async ({ asLead: { page, team, api }, adminApi }) => {
    const source = await createAlertingSource(adminApi, team, { runbook: APPROVAL_RUNBOOK });
    try {
      const workflowId = `wf-${randomUUID().slice(0, 8)}`;
      await source.fire(workflowId);
      const alert = await waitForAlert(api, team, `Settlement ${workflowId} failed`);
      const detail = new AlertDetailPage(page);
      await detail.goto(alert.id);

      await detail.decision(1, "Approve step").click({ timeout: PIPELINE_TIMEOUT });
      await expect(detail.approveDialog).toContainText(`Restarts settlement-${workflowId}.`);
      await detail.approveDialog.getByRole("button", { name: "Approve step" }).click();

      await expect(page.getByText("Step approved")).toBeVisible();
      await expect(detail.decision(1, "Approve step")).toHaveCount(0);
    } finally {
      await source.cleanup();
    }
  });

  test("a member sees no Approve button and the API refuses the approval", async ({
    asMember: { page, team, api },
    adminApi,
  }) => {
    const source = await createAlertingSource(adminApi, team, { runbook: APPROVAL_RUNBOOK });
    try {
      const workflowId = `wf-${randomUUID().slice(0, 8)}`;
      await source.fire(workflowId);
      const alert = await waitForAlert(api, team, `Settlement ${workflowId} failed`);
      const detail = new AlertDetailPage(page);
      await detail.goto(alert.id);

      await expect(detail.step(1)).toContainText("Waiting for a team lead to approve.", { timeout: PIPELINE_TIMEOUT });
      await expect(detail.decision(1, "Approve step")).toHaveCount(0);
      expect((await api.call(decideStep, alert.id, 0, approve)).status).toBe(403);
    } finally {
      await source.cleanup();
    }
  });

  test("a member marks a manual step as done; a viewer of the team cannot", async ({
    asMember: { page, team, api },
    asViewer,
    adminApi,
  }) => {
    const source = await createAlertingSource(adminApi, team, { runbook: MANUAL_RUNBOOK });
    try {
      const workflowId = `wf-${randomUUID().slice(0, 8)}`;
      await source.fire(workflowId);
      const alert = await waitForAlert(api, team, `Settlement ${workflowId} failed`);
      const detail = new AlertDetailPage(page);
      await detail.goto(alert.id);

      await detail.decision(1, "Mark as done").click({ timeout: PIPELINE_TIMEOUT });

      await expect(detail.step(1)).toContainText("Succeeded");
      const run = await api.callExpecting(getRunbookRun, 200, alert.id);
      expect(run?.steps[0].status).toBe("succeeded");
      await adminApi
        .callExpecting(setTeamMember, 200, team.id, asViewer.user.id, viewer)
        .catch(skipIfNotImplemented);
      expect((await asViewer.api.call(decideStep, alert.id, 0, done)).status).toBe(403);
    } finally {
      await source.cleanup();
    }
  });
});
