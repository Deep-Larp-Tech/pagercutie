import * as zod from 'zod'

/**
 * Audit log filters in the address (`?entity_type=alert&entity_id=…`), named like the `GET /audit` query params. A
 * hand-edited value that does not parse is dropped, so the page falls back to the unfiltered log.
 */
export const auditSearch = zod.object({
  /** Entity type as the API records it, e.g. `alert` or `rule`; the API keeps it as free text (at most 50 chars). */
  entity_type: zod.string().trim().min(1).max(50).optional().catch(undefined),
  /** Id of one entity; any 8-4-4-4-12 hex id, since the API accepts every UUID. */
  entity_id: zod.guid().optional().catch(undefined),
})

/** The audit log filters a page shows. */
export type AuditFilters = zod.infer<typeof auditSearch>

/**
 * Plain words for the audit actions PagerCutie records (`UI-6`). `AuditEntryRead.action` is a free string in the
 * contract (examples `alert.acknowledged`, `step.approved`), so this is a lookup with a fallback, not an exhaustive map.
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

/** An audit entity type in plain words: `event_schema` → "Event schema". Free text in the contract, like `action`. */
export function entityTypeLabel(entityType: string): string {
  return words(entityType, 'Unknown')
}
