import type { EventSchemaRead, RuleRead, RunbookRead } from '@/api/generated/model'
import { getListEventSchemasUrl, listEventSchemas } from '@/api/generated/event-schemas/event-schemas'
import { getListRunbooksUrl, listRunbooks } from '@/api/generated/runbooks/runbooks'
import { respond } from './http'
import { server } from './server'
import { settlements } from './teams'

/** Team Settlements' rule from SPEC §4.3, owned by the `settlements` test team. */
export function settlementsRule(overrides: Partial<RuleRead> = {}): RuleRead {
  return {
    id: 'rule-settlement-failed',
    name: 'Order settlement failed in prod',
    description: null,
    enabled: true,
    owner: { type: 'team', team_id: settlements.id },
    schema_ids: [workflowSchema.id],
    condition: {
      op: 'and',
      args: [
        { op: 'eq', field: 'payload.type', value: 'WORKFLOW_FAILED' },
        { op: 'eq', field: 'payload.workflowName', value: 'order-settlement' },
        { op: 'eq', field: 'payload.environment', value: 'prod' },
      ],
    },
    dedup: { fields: ['payload.workflowId'], window_s: 300 },
    routing: { recipients: [{ type: 'on_call', team_id: settlements.id }], channels: ['phone', 'sms'] },
    presentation: {
      title: 'Settlement {{payload.workflowId}} failed at {{payload.step}}',
      body: '{{payload.error.message}}',
      fields: ['payload.step', 'payload.error.message'],
      severity: 'critical',
      colour: 'red',
    },
    runbook_id: settlementTimeout.id,
    created_at: '2026-11-20T10:00:00Z',
    updated_at: '2026-11-20T10:00:00Z',
    ...overrides,
  }
}

function schema(name: string, properties: { [key: string]: unknown }): EventSchemaRead {
  return {
    id: `schema-${name}`,
    name,
    version: 1,
    team_id: settlements.id,
    description: null,
    json_schema: { type: 'object', properties },
    created_at: '2026-11-01T00:00:00Z',
  }
}

/** The workflow events Team Settlements' rule reads. */
export const workflowSchema = schema('workflow', {
  type: { type: 'string', enum: ['WORKFLOW_FAILED', 'WORKFLOW_DONE'] },
  workflowName: { type: 'string' },
  workflowId: { type: 'string' },
  environment: { type: 'string' },
  step: { type: 'string' },
  error: { type: 'object', properties: { code: { type: 'string' }, message: { type: 'string' } } },
})

/** The trade events Team Rates' rule reads. */
export const tradeSchema = schema('trade', {
  type: { type: 'string' },
  desk: { type: 'string' },
  notional: { type: 'number' },
  currency: { type: 'string' },
  reason: { type: 'string' },
})

/** The runbook the Settlements rule attaches. */
export const settlementTimeout: RunbookRead = {
  id: 'runbook-settlement-timeout',
  slug: 'settlement-timeout',
  title: 'Settlement timeout',
  team_id: settlements.id,
  format: 'structured',
  original: 'steps: []',
  attach: null,
  steps: [],
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
}

/** Answers what every builder screen loads besides the rule: event schemas and the team's runbooks. */
export function withBuilderData(teamId: string | null = settlements.id) {
  server.use(respond(listEventSchemas, 'get', getListEventSchemasUrl(), 200, [workflowSchema, tradeSchema]))
  if (teamId !== null) server.use(respond(listRunbooks, 'get', getListRunbooksUrl(), 200, [settlementTimeout]))
}
