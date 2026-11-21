import { useState } from 'react'
import type { AlertField, AlertRead, JsonValue } from '@/api/generated/model'
import { AlertCard } from '@/components/alerts/alert-card'
import type { RuleDraft } from '@/lib/rule-draft'
import { lookupPath, renderTemplate } from '@/lib/templates'

/** The alert of a preview that has no sample value for a field. */
const NO_VALUE = '…'

function jsonValue(value: unknown): JsonValue {
  if (value === undefined || value === null) return NO_VALUE
  return value
}

/** Props for `RulePreview`. */
export interface RulePreviewProps {
  draft: Pick<RuleDraft, 'title' | 'body' | 'fields' | 'severity' | 'colour'>
  /** Owning team; `null` for a personal rule. */
  teamId: string | null
  /** The test panel's sample event (`{source, severity, schema_id, payload}`), or `null` while it is not valid JSON. */
  event: unknown
}

/**
 * The alert this rule would raise, drawn with the feed's `AlertCard` in the rule's colour (DESIGN.md §1, `UI-5`). Title,
 * body and fields are filled from the sample event; a placeholder without a sample value stays as written.
 */
export function RulePreview({ draft, teamId, event }: RulePreviewProps) {
  const render = (template: string) => (event === null ? template : renderTemplate(template, event))
  const [now] = useState(() => new Date().toISOString())
  const fields: AlertField[] = draft.fields.map((path) => ({
    path,
    value: event === null ? NO_VALUE : jsonValue(lookupPath(event, path)),
  }))
  const alert: AlertRead = {
    id: 'preview',
    rule_id: 'preview',
    team_id: teamId,
    fingerprint: 'preview',
    status: 'open',
    severity: draft.severity,
    colour: draft.colour,
    title: draft.title.trim() === '' ? 'Your alert title shows here' : render(draft.title),
    body: draft.body.trim() === '' ? null : render(draft.body),
    fields,
    occurrences: 1,
    first_seen_at: now,
    last_seen_at: now,
    acknowledged_by: null,
    acknowledged_at: null,
    resolved_by: null,
    resolved_at: null,
    resolution: null,
    escalated_team_ids: [],
    payload: {},
  }
  return (
    <div aria-label="Alert preview" role="figure" className="flex flex-col gap-2">
      <AlertCard alert={alert} actions={false} />
      <p className="text-[12px]/[16px] text-muted-foreground">
        Filled from the sample event in the test panel. Real alerts also show a counter when the event repeats.
      </p>
    </div>
  )
}
