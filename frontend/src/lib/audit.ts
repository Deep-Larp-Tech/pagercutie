/**
 * Plain words for the audit actions an alert's history can hold. `AuditEntryRead.action` is a free string in the
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

/** `alert.auto_resolved` as "Alert auto resolved": the fallback for an action without words above. */
function humanise(action: string): string {
  const text = action.replaceAll(/[._]+/g, ' ').trim()
  return text === '' ? 'Unknown action' : text.charAt(0).toUpperCase() + text.slice(1)
}

/** What an audit action says happened, in plain words. */
export function auditActionText(action: string): string {
  return actionWords.get(action) ?? humanise(action)
}
