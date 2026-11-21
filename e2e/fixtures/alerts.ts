import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { listAlerts } from "../../frontend/src/api/generated/alerts/alerts";
import { createEventSchema } from "../../frontend/src/api/generated/event-schemas/event-schemas";
import type {
  AlertRead,
  RuleCreate,
  RunbookCreate,
  RunbookRead,
  SourceCreate,
  TeamRead,
} from "../../frontend/src/api/generated/model";
import { createRule, deleteRule } from "../../frontend/src/api/generated/rules/rules";
import { createRunbook, deleteRunbook } from "../../frontend/src/api/generated/runbooks/runbooks";
import { createSource, deleteSource, rotateSourceToken } from "../../frontend/src/api/generated/sources/sources";
import type { ApiClient } from "./api";
import { ignoreNotImplemented, skipIfNotImplemented } from "./implemented";

/**
 * Origin of the ingest role (`POST /ingest/{slug}`). Compose publishes no host port for it and `/api` reaches only
 * the API role, so specs that fire events skip unless this is set, e.g. `E2E_INGEST_URL=http://localhost:8001`.
 */
export const INGEST_URL = process.env.E2E_INGEST_URL;

/** A webhook source in a team with a rule that turns every event into a critical alert, one per `workflowId`. */
export interface AlertingSource {
  /** Sends one event with `workflowId`; the alert's title is `Settlement <workflowId> failed`. */
  fire: (workflowId: string) => Promise<void>;
  /** Deletes the rule and the source; ignores delete routes that are still stubs. */
  cleanup: () => Promise<void>;
}

/** Skips the current test unless `E2E_INGEST_URL` is set; returns the ingest origin. */
export function requireIngest(): string {
  test.skip(INGEST_URL === undefined, "E2E_INGEST_URL is not set: no way to fire events at the ingest role");
  if (INGEST_URL === undefined) throw new Error("unreachable: test.skip throws");
  return INGEST_URL;
}

/** Options for `createAlertingSource`. */
export interface AlertingSourceOptions {
  /** Structured runbook YAML (SPEC §11.4) to attach to the rule, so each alert gets a runbook run. */
  runbook?: string;
}

/**
 * Creates an event schema, a webhook source and a rule owned by `team` (SPEC §4.3), so `fire` makes the pipeline
 * create or repeat an alert in the team's feed. Skips the test while a setup route is a stub.
 */
export async function createAlertingSource(
  adminApi: ApiClient,
  team: TeamRead,
  options: AlertingSourceOptions = {},
): Promise<AlertingSource> {
  const ingestUrl = requireIngest();
  const suffix = randomUUID().slice(0, 8);
  const schema = await adminApi
    .callExpecting(createEventSchema, 201, {
      name: `e2e-${suffix}`,
      version: 1,
      team_id: team.id,
      json_schema: {
        type: "object",
        properties: { workflowId: { type: "string" } },
        required: ["workflowId"],
      },
    })
    .catch(skipIfNotImplemented);
  const sourceCreate: SourceCreate = {
    slug: `e2e-${suffix}`,
    name: `E2E source ${suffix}`,
    type: "webhook",
    team_id: team.id,
  };
  const source = await adminApi.callExpecting(createSource, 201, sourceCreate).catch(skipIfNotImplemented);
  const { token } = await adminApi.callExpecting(rotateSourceToken, 200, source.id).catch(skipIfNotImplemented);
  let runbook: RunbookRead | undefined;
  if (options.runbook !== undefined) {
    const runbookCreate: RunbookCreate = {
      slug: `e2e-${suffix}`,
      title: `E2E runbook ${suffix}`,
      team_id: team.id,
      format: "structured",
      original: options.runbook,
    };
    runbook = await adminApi.callExpecting(createRunbook, 201, runbookCreate).catch(skipIfNotImplemented);
  }
  const ruleCreate: RuleCreate = {
    name: `E2E rule ${suffix}`,
    owner: { type: "team", team_id: team.id },
    schema_ids: [schema.id],
    condition: { op: "exists", field: "payload.workflowId" },
    dedup: { fields: ["payload.workflowId"] },
    routing: { recipients: [{ type: "team", team_id: team.id }] },
    presentation: {
      title: "Settlement {{payload.workflowId}} failed",
      fields: ["payload.workflowId"],
      severity: "critical",
      colour: "red",
    },
    runbook_id: runbook?.id,
  };
  const rule = await adminApi.callExpecting(createRule, 201, ruleCreate).catch(skipIfNotImplemented);

  return {
    fire: async (workflowId) => {
      const response = await fetch(new URL(`/ingest/${source.slug}`, ingestUrl), {
        method: "POST",
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: JSON.stringify({ workflowId }),
      });
      if (!response.ok) throw new Error(`POST /ingest/${source.slug} answered ${response.status}`);
    },
    cleanup: async () => {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteRule, 204, rule.id));
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteSource, 204, source.id));
      const created = runbook;
      if (created !== undefined) {
        await ignoreNotImplemented(() => adminApi.callExpecting(deleteRunbook, 204, created.id));
      }
    },
  };
}

/** How long the pipeline may take to turn a fired event into an alert (ms). */
export const PIPELINE_TIMEOUT = 15_000;

/** Waits until `api` lists an alert titled `title` in `team`'s feed and returns it. */
export async function waitForAlert(api: ApiClient, team: TeamRead, title: string): Promise<AlertRead> {
  let found: AlertRead | undefined;
  await expect
    .poll(
      async () => {
        const response = await api.call(listAlerts, { team_id: team.id });
        found = response.status === 200 ? response.data.find((alert) => alert.title === title) : undefined;
        return found !== undefined;
      },
      { timeout: PIPELINE_TIMEOUT },
    )
    .toBe(true);
  if (found === undefined) throw new Error(`No alert titled ${title}`);
  return found;
}
