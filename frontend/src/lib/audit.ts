import * as zod from 'zod'
import { AuditEntityType } from '@/api/generated/model'

/**
 * Audit log filters in the address (`?entity_type=alert&entity_id=…`), named like the `GET /audit` query params. A
 * hand-edited value that does not parse is dropped, so the page falls back to the unfiltered log.
 */
export const auditSearch = zod.object({
  /** One of the entity types the API records (`AuditEntityType`), e.g. `alert` or `rule`. */
  entity_type: zod.enum(AuditEntityType).optional().catch(undefined),
  /** Id of one entity; any 8-4-4-4-12 hex id, since the API accepts every UUID. */
  entity_id: zod.guid().optional().catch(undefined),
})

/** The audit log filters a page shows. */
export type AuditFilters = zod.infer<typeof auditSearch>

/**
 * Plain words for some of the audit actions PagerCutie records (`UI-6`); the others read as their own words. Lookup
 * with a fallback until every `AuditAction` member has a phrase.
 */
const actionWords: ReadonlyMap<string, string> = new Map([
  ['alert.created', 'Alert fired'],
  ['alert.occurred', 'Alert fired again'],
  ['alert.acknowledged', 'Acknowledged the alert'],
  ['alert.resolved', 'Resolved the alert'],
  ['alert.escalated', 'Escalated the alert'],
  ['step.started', 'Started a step'],
  ['step.succeeded', 'A step succeeded'],
  ['step.failed', 'A step failed'],
  ['step.skipped', 'Skipped a step'],
  ['step.approved', 'Approved a step'],
  ['step.rejected', 'Rejected a step'],
  ['step.answered', 'Answered a step question'],
  ['step.done', 'Marked a step done'],
  ['delivery.sent', 'Sent a notification'],
  ['delivery.failed', 'A notification failed'],
])

/** `snake_case` or dotted API words as a sentence-case phrase: `event_schema.version_added` → "Event schema version added". */
function words(value: string, empty: string): string {
  const phrase = value.replaceAll(/[._]+/g, ' ').trim()
  return phrase === '' ? empty : phrase.charAt(0).toUpperCase() + phrase.slice(1)
}

/** What an audit action says happened, in plain words; actions without an entry above read as their own words. */
export function auditActionText(action: string): string {
  return actionWords.get(action) ?? words(action, 'Unknown action')
}

/** An audit entity type in plain words: `event_schema` → "Event schema". */
export function entityTypeLabel(entityType: string): string {
  return words(entityType, 'Unknown')
}
