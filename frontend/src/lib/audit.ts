import * as zod from 'zod'
import { AuditAction, AuditEntityType, type ListAuditEntriesParams } from '@/api/generated/model'

/** Time range presets of the audit log, newest entries back to this long ago; no preset means all time. */
export const auditRanges = ['1h', '24h', '7d', '30d'] as const

/** One of `auditRanges`. */
export type AuditRange = (typeof auditRanges)[number]

/** Length of each time range preset (ms). */
const rangeMs = {
  '1h': 60 * 60_000,
  '24h': 24 * 60 * 60_000,
  '7d': 7 * 24 * 60 * 60_000,
  '30d': 30 * 24 * 60 * 60_000,
} satisfies Record<AuditRange, number>

/** Segmented control label of each time range preset. */
export const rangeLabel = {
  '1h': 'Last hour',
  '24h': 'Last 24 hours',
  '7d': 'Last 7 days',
  '30d': 'Last 30 days',
} satisfies Record<AuditRange, string>

/**
 * Audit log filters in the address, named like the `GET /audit` query params except `range`, a time range preset the
 * page turns into `since` (relative, so a shared link keeps meaning "the last 24 hours"). `action` holds one action.
 * A hand-edited value that does not parse is dropped, so the page falls back to the unfiltered log.
 */
export const auditSearch = zod.object({
  /** One of the entity types the API records (`AuditEntityType`), e.g. `alert` or `rule`. */
  entity_type: zod.enum(AuditEntityType).optional().catch(undefined),
  /** Id of one entity; any 8-4-4-4-12 hex id, since the API accepts every UUID. */
  entity_id: zod.guid().optional().catch(undefined),
  /** One `AuditAction`. */
  action: zod.enum(AuditAction).optional().catch(undefined),
  /** Id of the user who did it. */
  actor_user_id: zod.guid().optional().catch(undefined),
  /** Only what the system did; `actor_user_id` wins when both are set. */
  system: zod.literal(true).optional().catch(undefined),
  /** Team whose entries to list; the admin page only, a team page always lists its own team. */
  team_id: zod.guid().optional().catch(undefined),
  /** Only entries without a team (admin page); `team_id` wins when both are set. */
  without_team: zod.literal(true).optional().catch(undefined),
  /** Time range preset; absent for all time. */
  range: zod.enum(auditRanges).optional().catch(undefined),
})

/** The audit log filters a page shows. */
export type AuditFilters = zod.infer<typeof auditSearch>

/**
 * `GET /audit` params for the filters: `teamId` (a team page) replaces the address's team, a range becomes `since`
 * counted back from `anchor` (epoch ms), and of each pair the API rejects together only the specific one is sent.
 */
export function auditQuery(filters: AuditFilters, teamId: string | undefined, anchor: number): ListAuditEntriesParams {
  const team = teamId ?? filters.team_id
  return {
    team_id: team,
    without_team: team === undefined && filters.without_team === true ? true : undefined,
    entity_type: filters.entity_type,
    entity_id: filters.entity_id,
    actor_user_id: filters.actor_user_id,
    system: filters.actor_user_id === undefined && filters.system === true ? true : undefined,
    action: filters.action === undefined ? undefined : [filters.action],
    since: filters.range === undefined ? undefined : new Date(anchor - rangeMs[filters.range]).toISOString(),
  }
}

/** Whether any filter is set; `team_id` counts only on the admin page, where it is a filter. */
export function isFiltered(filters: AuditFilters): boolean {
  return Object.values(filters).some((value) => value !== undefined)
}

/** The entity type every entry with an action names; mirrors `entity_type_of` in the backend. */
export const actionEntityType = {
  'user.created': 'user',
  'user.updated': 'user',
  'user.deleted': 'user',
  'user.channel_preferences_updated': 'user',
  'team.created': 'team',
  'team.updated': 'team',
  'team.deleted': 'team',
  'team.member_added': 'team',
  'team.member_role_changed': 'team',
  'team.member_removed': 'team',
  'team.channel_preferences_updated': 'team',
  'team.rotation_updated': 'team',
  'source.created': 'source',
  'source.updated': 'source',
  'source.deleted': 'source',
  'source.token_rotated': 'source',
  'event_schema.created': 'event_schema',
  'rule.created': 'rule',
  'rule.updated': 'rule',
  'rule.deleted': 'rule',
  'runbook.created': 'runbook',
  'runbook.updated': 'runbook',
  'runbook.deleted': 'runbook',
  'alert.created': 'alert',
  'alert.renotified': 'alert',
  'alert.acknowledged': 'alert',
  'alert.resolved': 'alert',
  'alert.escalated': 'alert',
  'step.awaiting_approval': 'alert',
  'step.awaiting_answer': 'alert',
  'step.awaiting_manual': 'alert',
  'step.started': 'alert',
  'step.succeeded': 'alert',
  'step.failed': 'alert',
  'step.skipped': 'alert',
  'step.approved': 'alert',
  'step.rejected': 'alert',
  'step.answered': 'alert',
  'step.done': 'alert',
  'runbook_run.started': 'alert',
  'runbook_run.finished': 'alert',
  'step.retry_failed': 'alert',
} satisfies Record<AuditAction, AuditEntityType>

/** What each audit action says happened, in plain words (`UI-6`); reads after "You:" or a name in the alert history. */
const actionWords = {
  'user.created': 'Added a user',
  'user.updated': "Changed a user's profile",
  'user.deleted': 'Deleted a user',
  'user.channel_preferences_updated': "Changed a user's channel preferences",
  'team.created': 'Created the team',
  'team.updated': 'Renamed or described the team',
  'team.deleted': 'Deleted the team',
  'team.member_added': 'Added a team member',
  'team.member_role_changed': "Changed a member's role",
  'team.member_removed': 'Removed a team member',
  'team.channel_preferences_updated': "Changed the team's channel preferences",
  'team.rotation_updated': 'Changed the on-call rotation',
  'source.created': 'Added a source',
  'source.updated': 'Changed a source',
  'source.deleted': 'Deleted a source',
  'source.token_rotated': 'Replaced the ingest token',
  'event_schema.created': 'Added an event schema version',
  'rule.created': 'Created a rule',
  'rule.updated': 'Changed a rule',
  'rule.deleted': 'Deleted a rule',
  'runbook.created': 'Created a runbook',
  'runbook.updated': 'Changed a runbook',
  'runbook.deleted': 'Deleted a runbook',
  'alert.created': 'Alert fired',
  'alert.renotified': 'Alert fired again',
  'alert.acknowledged': 'Acknowledged the alert',
  'alert.resolved': 'Resolved the alert',
  'alert.escalated': 'Escalated the alert',
  'step.awaiting_approval': 'A step is waiting for approval',
  'step.awaiting_answer': 'A step is waiting for an answer',
  'step.awaiting_manual': 'A manual step is waiting',
  'step.started': 'Started a step',
  'step.succeeded': 'A step succeeded',
  'step.failed': 'A step failed',
  'step.skipped': 'Skipped a step',
  'step.approved': 'Approved a step',
  'step.rejected': 'Rejected a step',
  'step.answered': 'Answered a step question',
  'step.done': 'Marked a step done',
  'runbook_run.started': 'Started the runbook',
  'runbook_run.finished': 'Finished the runbook',
  'step.retry_failed': 'A retry failed, so it ran again',
} satisfies Record<AuditAction, string>

/** What an audit action says happened, in plain words. */
export function auditActionText(action: AuditAction): string {
  return actionWords[action]
}

/** Each entity type in plain words, singular. */
const entityTypeWords = {
  user: 'User',
  team: 'Team',
  source: 'Source',
  event_schema: 'Event schema',
  rule: 'Rule',
  runbook: 'Runbook',
  alert: 'Alert',
} satisfies Record<AuditEntityType, string>

/** An audit entity type in plain words: `event_schema` → "Event schema". */
export function entityTypeLabel(entityType: AuditEntityType): string {
  return entityTypeWords[entityType]
}

/** Every entity type, in the order the filters list them. */
export const auditEntityTypes: readonly AuditEntityType[] = Object.values(AuditEntityType)

/** The actions whose entries name `entityType`, in declaration order. */
export function actionsOf(entityType: AuditEntityType): AuditAction[] {
  return Object.values(AuditAction).filter((action) => actionEntityType[action] === entityType)
}
