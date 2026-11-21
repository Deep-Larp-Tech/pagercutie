import { getListAlertsUrl, listAlerts } from '@/api/generated/alerts/alerts'
import type {
  AlertRead,
  AuditEntryRead,
  DeliveryRead,
  RunbookRunRead,
  Step,
  StepRunRead,
  TeamRead,
} from '@/api/generated/model'
import { getGetTeamOnCallUrl, getTeamOnCall } from '@/api/generated/teams/teams'
import { respond } from './http'
import { team } from './people'

let sequence = 0

/** A UUID no other call returns; the live feed validates ids as UUIDs, so stream fixtures need real ones. */
export function uuid(): string {
  sequence += 1
  return `0193b000-0000-7000-8000-${sequence.toString(16).padStart(12, '0')}`
}

/** A team whose id is a UUID, for alerts sent through the stream. */
export function uuidTeam(slug: string, name: string): TeamRead {
  return { ...team(slug, name), id: uuid() }
}

/** An open critical alert in red from `teamId`, first and last seen at 12:00; override any field. */
export function alert(teamId: string | null, overrides: Partial<AlertRead> = {}): AlertRead {
  return {
    id: uuid(),
    rule_id: uuid(),
    team_id: teamId,
    fingerprint: 'wf-8f21',
    status: 'open',
    severity: 'critical',
    colour: 'red',
    title: 'Settlement wf-8f21 failed at reserve-funds',
    body: 'Retries exhausted after 3 attempts.',
    fields: [
      { path: 'payload.workflowId', value: 'wf-8f21' },
      { path: 'payload.amount', value: 12400000 },
    ],
    occurrences: 1,
    first_seen_at: '2026-11-21T12:00:00Z',
    last_seen_at: '2026-11-21T12:00:00Z',
    acknowledged_by: null,
    acknowledged_at: null,
    resolved_by: null,
    resolved_at: null,
    resolution: null,
    escalated_team_ids: [],
    payload: {},
    ...overrides,
  }
}

/**
 * Handlers for the endpoints the Overview and the team alerts page call on load, answering with no alerts and no
 * rotation; for tests about something else on those pages (the shell, sign-in).
 */
export function quietFeedEndpoints() {
  return [
    respond(listAlerts, 'get', getListAlertsUrl(), 200, []),
    respond(getTeamOnCall, 'get', getGetTeamOnCallUrl(':teamId'), 200, {
      team_id: '',
      user: null,
      until: null,
    }),
  ]
}

/** A step run at `index` that has not started; override any field. */
export function stepRun(index: number, step: Step, overrides: Partial<StepRunRead> = {}): StepRunRead {
  return {
    index,
    step,
    status: 'pending',
    attempts: 0,
    failures: 0,
    result: null,
    decided_by: null,
    decided_at: null,
    ...overrides,
  }
}

/** The runbook run of `alertId` with `steps`. */
export function runbookRun(alertId: string, steps: StepRunRead[]): RunbookRunRead {
  return { id: uuid(), alert_id: alertId, runbook_id: uuid(), steps }
}

/** An SMS to `userId` about `alertId`, sent at 12:01; override any field. */
export function delivery(alertId: string, userId: string, overrides: Partial<DeliveryRead> = {}): DeliveryRead {
  return {
    id: uuid(),
    alert_id: alertId,
    user_id: userId,
    channel: 'sms',
    status: 'sent',
    attempts: 1,
    last_error: null,
    message: 'CRITICAL Settlement wf-8f21 failed at reserve-funds',
    created_at: '2026-11-21T12:00:30Z',
    sent_at: '2026-11-21T12:01:00Z',
    ...overrides,
  }
}

/** An audit entry about `alertId` with `action` by `actorUserId` (`null`: the system), at 12:05. */
export function auditEntry(alertId: string, actorUserId: string | null, action: string): AuditEntryRead {
  return {
    id: uuid(),
    at: '2026-11-21T12:05:00Z',
    actor_user_id: actorUserId,
    action,
    entity_type: 'alert',
    entity_id: alertId,
    team_id: null,
    data: {},
  }
}
