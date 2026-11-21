import { getListAlertsUrl, listAlerts } from '@/api/generated/alerts/alerts'
import type { AlertRead, TeamRead } from '@/api/generated/model'
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
