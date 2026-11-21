import { randomUUID } from "node:crypto";
import type { RunbookCreate, RunbookRead, TeamRead } from "../../frontend/src/api/generated/model";
import { createRunbook } from "../../frontend/src/api/generated/runbooks/runbooks";
import type { ApiClient } from "./api";
import { skipIfNotImplemented } from "./implemented";

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

/** Creates a runbook through the API as `api`; skips the test while `POST /runbooks` is a stub. */
export async function seedRunbook(api: ApiClient, team: TeamRead, title?: string): Promise<RunbookRead> {
  return api.callExpecting(createRunbook, 201, markdownRunbook(team, title)).catch(skipIfNotImplemented);
}
