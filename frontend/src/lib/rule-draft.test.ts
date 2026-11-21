import { describe, expect, test } from 'vitest'
import type { RuleRead } from '@/api/generated/model'
import {
  draftFromRule,
  newDraft,
  placeIssues,
  toCreate,
  toUpdate,
  validateDraft,
  windowDraft,
  windowSeconds,
  withSeverity,
} from './rule-draft'

/** Team Settlements' rule from SPEC §4.3, with UUIDs replaced by readable ids. */
const settlementsRule: RuleRead = {
  id: 'rule-settlement-failed',
  name: 'Order settlement failed in prod',
  description: null,
  enabled: true,
  owner: { type: 'team', team_id: 'team-settlements' },
  schema_ids: ['schema-workflow'],
  condition: {
    op: 'and',
    args: [
      { op: 'eq', field: 'payload.type', value: 'WORKFLOW_FAILED' },
      { op: 'eq', field: 'payload.workflowName', value: 'order-settlement' },
      { op: 'eq', field: 'payload.environment', value: 'prod' },
    ],
  },
  dedup: { fields: ['payload.workflowId'], window_s: 300 },
  routing: { recipients: [{ type: 'on_call', team_id: 'team-settlements' }], channels: ['phone', 'sms'] },
  presentation: {
    title: 'Settlement {{payload.workflowId}} failed at {{payload.step}}',
    body: '{{payload.error.message}}',
    fields: ['payload.step', 'payload.error.message'],
    severity: 'critical',
    colour: 'red',
  },
  runbook_id: 'runbook-settlement-timeout',
  created_at: '2026-11-20T10:00:00Z',
  updated_at: '2026-11-20T10:00:00Z',
}

function parts(draft: ReturnType<typeof newDraft>) {
  const result = validateDraft(draft)
  if (!result.ok) throw new Error(JSON.stringify(result.errors))
  return result.parts
}

describe('rule draft', () => {
  test('a saved rule round-trips into the same create body', () => {
    const body = toCreate(parts(draftFromRule(settlementsRule)), settlementsRule.owner)

    expect(body).toEqual({
      name: settlementsRule.name,
      description: null,
      enabled: true,
      owner: settlementsRule.owner,
      schema_ids: settlementsRule.schema_ids,
      condition: settlementsRule.condition,
      dedup: settlementsRule.dedup,
      routing: settlementsRule.routing,
      presentation: settlementsRule.presentation,
      runbook_id: settlementsRule.runbook_id,
    })
  })

  test('an unchanged rule sends an empty PATCH; a change sends only that part', () => {
    const draft = draftFromRule(settlementsRule)

    expect(toUpdate(parts(draft), settlementsRule)).toEqual({})
    expect(toUpdate(parts({ ...draft, name: 'Renamed', windowValue: '10' }), settlementsRule)).toEqual({
      name: 'Renamed',
      dedup: { fields: ['payload.workflowId'], window_s: 600 },
    })
  })

  test('emptying the description or runbook sends null, which clears them', () => {
    const rule = { ...settlementsRule, description: 'Pages the on-call person' }
    const draft = { ...draftFromRule(rule), description: '', runbookId: null }

    expect(toUpdate(parts(draft), rule)).toEqual({ description: null, runbook_id: null })
  })

  test('the colour follows the severity until picked by hand; a saved colour counts as picked', () => {
    const fresh = newDraft([])
    expect(fresh.colour).toBe('red')
    expect(withSeverity(fresh, 'warn').colour).toBe('yellow')

    const picked = withSeverity({ ...fresh, colour: 'green', colourTouched: true }, 'info')
    expect(picked).toMatchObject({ severity: 'info', colour: 'green' })

    expect(withSeverity(draftFromRule(settlementsRule), 'info').colour).toBe('red')
  })

  test('the dedup window shows in the largest unit that divides it', () => {
    expect(windowDraft(300)).toEqual({ windowValue: '5', windowUnit: 'minutes' })
    expect(windowDraft(7200)).toEqual({ windowValue: '2', windowUnit: 'hours' })
    expect(windowDraft(90)).toEqual({ windowValue: '90', windowUnit: 'seconds' })
    expect(windowSeconds({ windowValue: '25', windowUnit: 'hours' })).toBeNull()
    expect(windowSeconds({ windowValue: '1.5', windowUnit: 'minutes' })).toBeNull()
  })

  test('a new draft is invalid until named, titled and given a condition', () => {
    const result = validateDraft(newDraft([]))

    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.errors.fields).toEqual({
      name: 'Give the rule a name.',
      recipients: 'Add at least one recipient.',
      title: 'Write a title, e.g. Settlement {{payload.workflowId}} failed.',
    })
    expect(Object.values(result.errors.nodes)).toEqual([{ field: 'Pick or type a field.', value: 'Enter a value.' }])
  })

  test('422 errors land under their field or condition node', () => {
    const draft = draftFromRule(settlementsRule)
    const second = draft.condition.children[1]

    const errors = placeIssues(draft, [
      { path: ['name'], message: 'Too long' },
      { path: ['condition', 'and', 'args', 1, 'eq', 'value'], message: 'Bad value' },
      { path: ['routing', 'recipients', 0, 'on_call', 'team_id'], message: 'Unknown team' },
      { path: ['presentation', 'title'], message: 'Bad template' },
      { path: ['dedup', 'window_s'], message: 'Too long a window' },
      { path: ['owner'], message: 'Owner mismatch' },
    ])

    expect(errors).toEqual({
      fields: { name: 'Too long', recipients: 'Unknown team', title: 'Bad template', window: 'Too long a window' },
      nodes: { [second?.id ?? '']: { value: 'Bad value' } },
      root: "Couldn't save the rule. Owner mismatch",
    })
  })
})
