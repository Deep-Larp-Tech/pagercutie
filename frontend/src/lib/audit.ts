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

/** `snake_case` or dotted API words as a sentence-case phrase: `event_schema.version_added` → "Event schema version added". */
function words(value: string): string {
  const phrase = value.replaceAll(/[._]+/g, ' ').trim()
  return phrase.charAt(0).toUpperCase() + phrase.slice(1)
}

/**
 * An audit action in plain words (`UI-6`): `alert.acknowledged` → "Alert acknowledged". `action` is free text in the
 * contract (no enum), so this reads every value instead of mapping a closed set.
 */
export function actionLabel(action: string): string {
  return words(action)
}

/** An audit entity type in plain words: `event_schema` → "Event schema". Free text in the contract, like `action`. */
export function entityTypeLabel(entityType: string): string {
  return words(entityType)
}
