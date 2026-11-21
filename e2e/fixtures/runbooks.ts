import { randomUUID } from "node:crypto";
import type { RunbookCreate, RunbookRead, TeamRead } from "../../frontend/src/api/generated/model";
import { createRunbook, deleteRunbook } from "../../frontend/src/api/generated/runbooks/runbooks";
import type { ApiClient } from "./api";
import { ignoreNotImplemented, skipIfNotImplemented } from "./implemented";

/** A Markdown runbook body for `team` with a unique slug, so parallel tests never collide. */
export function markdownRunbook(team: TeamRead, title = "E2E checklist"): RunbookCreate {
  return {
    team_id: team.id,
    slug: `e2e-${randomUUID()}`,
    title,
    format: "markdown",
    original: "1. Open the dashboard.\n2. Post an update in the incident channel.\n",
  };
}

/** The brief's settlement runbook (REQUIREMENTS §6.2, SPEC §11.4) as a structured body for `team`, unique slug. */
export function settlementRunbook(team: TeamRead): RunbookCreate {
  const slug = `e2e-${randomUUID()}`;
  return {
    slug,
    title: "E2E settlement timeout",
    team_id: team.id,
    format: "structured",
    original: `runbook: ${slug}
matches:
  type: WORKFLOW_FAILED
  "error.code": TIMEOUT
steps:
  - check: "Is counterparty-service healthy?"
    action: http_get
    url: "http://counterparty-service/health"
  - action: retry_workflow
    workflowId: "{{workflowId}}"
    approval: none
  - if: "retry fails twice"
    action: escalate
    team: counterparty-support
    approval: required
`,
  };
}

/** Creates a runbook from `body` as `api`; skips the test while `POST /runbooks` is a stub. */
export async function createTestRunbook(api: ApiClient, body: RunbookCreate): Promise<RunbookRead> {
  return api.callExpecting(createRunbook, 201, body).catch(skipIfNotImplemented);
}

/** Creates a Markdown runbook through the API as `api`; skips the test while `POST /runbooks` is a stub. */
export async function seedRunbook(api: ApiClient, team: TeamRead, title?: string): Promise<RunbookRead> {
  return createTestRunbook(api, markdownRunbook(team, title));
}

/** Deletes a runbook so the persona's team can be deleted; a runbook already deleted (404) is fine. */
export async function deleteTestRunbook(adminApi: ApiClient, runbook: RunbookRead): Promise<void> {
  await ignoreNotImplemented(async () => {
    const response = await adminApi.call(deleteRunbook, runbook.id);
    if (response.status !== 204 && response.status !== 404) {
      throw new Error(`deleteRunbook answered ${response.status}`);
    }
  });
}
