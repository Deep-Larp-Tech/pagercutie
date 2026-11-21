import type {
  Channel,
  Colour,
  Condition,
  Owner,
  Recipient,
  RuleCreate,
  RuleRead,
  RuleUpdate,
  Severity,
} from '@/api/generated/model'
import {
  createRuleBodyDedupFieldsMax,
  createRuleBodyDedupWindowSDefault,
  createRuleBodyDedupWindowSMax,
  createRuleBodyDescriptionOneMax,
  createRuleBodyNameMax,
  createRuleBodyPresentationBodyOneMax,
  createRuleBodyPresentationFieldsMax,
  createRuleBodyPresentationTitleMax,
  createRuleBodyRoutingRecipientsMax,
} from '@/api/generated/rules/rules.zod'
import { fieldPathProblem, fromRootCondition, locateIssue, newGroup, toRootCondition, type GroupDraft, type NodePart } from './rule-condition'
import { defaultColour } from './severity'
import type { BodyIssue } from './validation-errors'

/** Unit the dedup window is shown in; stored as seconds (`Dedup.window_s`). */
export type WindowUnit = 'seconds' | 'minutes' | 'hours'

/** Seconds per window unit. */
export const windowUnitSeconds = {
  seconds: 1,
  minutes: 60,
  hours: 3600,
} as const satisfies Record<WindowUnit, number>

/** A rule as the builder edits it. Turned into `RuleCreate` or `RuleUpdate` by `toCreate` and `toUpdate`. */
export interface RuleDraft {
  name: string
  /** Empty means no description. */
  description: string
  enabled: boolean
  /** Event schemas the rule applies to; empty means any. */
  schemaIds: string[]
  condition: GroupDraft
  recipients: Recipient[]
  /** Channels for every recipient; `null` uses each recipient's channel preferences (`DEL-2`). */
  channels: Channel[] | null
  title: string
  /** Empty means no body. */
  body: string
  /** Event fields listed on the alert. */
  fields: string[]
  severity: Severity
  colour: Colour
  /** The author picked the colour, so a new severity no longer changes it (DESIGN.md §4.3). */
  colourTouched: boolean
  dedupFields: string[]
  /** Window length as typed, in `windowUnit`. */
  windowValue: string
  windowUnit: WindowUnit
  runbookId: string | null
}

/** Builder fields an error can sit under, besides the condition's nodes. */
export type DraftField =
  | 'name'
  | 'description'
  | 'schemaIds'
  | 'recipients'
  | 'channels'
  | 'title'
  | 'body'
  | 'fields'
  | 'severity'
  | 'colour'
  | 'dedupFields'
  | 'window'
  | 'runbook'

/** Errors of one condition node. */
export type NodeErrors = Partial<Record<NodePart, string>>

/** Every error the builder shows: under a field, under a condition node, or above the Save button. */
export interface DraftErrors {
  fields: Partial<Record<DraftField, string>>
  /** Keyed by node id. */
  nodes: Partial<Record<string, NodeErrors>>
  root: string | null
}

/** No errors. */
export const NO_ERRORS: DraftErrors = { fields: {}, nodes: {}, root: null }

/** Whether there is any error to show. */
export function hasErrors(errors: DraftErrors): boolean {
  return errors.root !== null || Object.keys(errors.fields).length > 0 || Object.keys(errors.nodes).length > 0
}

/** The window in the largest unit that divides it, so 300 s reads as 5 minutes and 90 s stays 90 seconds. */
export function windowDraft(seconds: number): Pick<RuleDraft, 'windowValue' | 'windowUnit'> {
  if (seconds % 3600 === 0) return { windowValue: String(seconds / 3600), windowUnit: 'hours' }
  if (seconds % 60 === 0) return { windowValue: String(seconds / 60), windowUnit: 'minutes' }
  return { windowValue: String(seconds), windowUnit: 'seconds' }
}

/** A new rule: one empty predicate, `defaultRecipients`, critical in red, five-minute dedup window. */
export function newDraft(defaultRecipients: Recipient[]): RuleDraft {
  return {
    name: '',
    description: '',
    enabled: true,
    schemaIds: [],
    condition: newGroup('and'),
    recipients: defaultRecipients,
    channels: null,
    title: '',
    body: '',
    fields: [],
    severity: 'critical',
    colour: defaultColour.critical,
    colourTouched: false,
    dedupFields: [],
    ...windowDraft(createRuleBodyDedupWindowSDefault),
    runbookId: null,
  }
}

/** The builder's draft of a saved rule. Its colour counts as picked, so changing the severity keeps it. */
export function draftFromRule(rule: RuleRead): RuleDraft {
  return {
    name: rule.name,
    description: rule.description ?? '',
    enabled: rule.enabled,
    schemaIds: rule.schema_ids,
    condition: fromRootCondition(rule.condition),
    recipients: rule.routing.recipients,
    channels: rule.routing.channels ?? null,
    title: rule.presentation.title,
    body: rule.presentation.body ?? '',
    fields: rule.presentation.fields ?? [],
    severity: rule.presentation.severity,
    colour: rule.presentation.colour,
    colourTouched: true,
    dedupFields: rule.dedup.fields ?? [],
    ...windowDraft(rule.dedup.window_s ?? createRuleBodyDedupWindowSDefault),
    runbookId: rule.runbook_id,
  }
}

/** The draft with a new severity; the colour follows it until the author picks one (DESIGN.md §4.3, ADR-0033). */
export function withSeverity(draft: RuleDraft, severity: Severity): RuleDraft {
  return { ...draft, severity, colour: draft.colourTouched ? draft.colour : defaultColour[severity] }
}

/** The window in seconds, or `null` when the typed value is not a whole number in range. */
export function windowSeconds(draft: Pick<RuleDraft, 'windowValue' | 'windowUnit'>): number | null {
  const value = Number(draft.windowValue)
  if (draft.windowValue.trim() === '' || !Number.isInteger(value)) return null
  const seconds = value * windowUnitSeconds[draft.windowUnit]
  return seconds >= 1 && seconds <= createRuleBodyDedupWindowSMax ? seconds : null
}

/** The parts of a rule both create and update send, built from a valid draft. */
interface RuleParts {
  name: string
  description: string | null
  enabled: boolean
  schema_ids: string[]
  condition: Condition
  dedup: { fields: string[]; window_s: number }
  routing: { recipients: Recipient[]; channels: Channel[] | null }
  presentation: { title: string; body: string | null; fields: string[]; severity: Severity; colour: Colour }
  runbook_id: string | null
}

/** The rule's parts, or every error that stops the draft from being sent. */
export function validateDraft(draft: RuleDraft): { ok: true; parts: RuleParts } | { ok: false; errors: DraftErrors } {
  const fields: DraftErrors['fields'] = {}
  const nodes: DraftErrors['nodes'] = {}
  const name = draft.name.trim()
  if (name === '') fields.name = 'Give the rule a name.'
  else if (name.length > createRuleBodyNameMax) fields.name = `Use at most ${createRuleBodyNameMax} characters.`
  if (draft.description.length > createRuleBodyDescriptionOneMax) {
    fields.description = `Use at most ${createRuleBodyDescriptionOneMax} characters.`
  }
  const condition = toRootCondition(draft.condition)
  if (!condition.ok) {
    for (const { nodeId, part, message } of condition.issues) nodes[nodeId] = { ...nodes[nodeId], [part]: message }
  }
  if (draft.recipients.length === 0) fields.recipients = 'Add at least one recipient.'
  else if (draft.recipients.length > createRuleBodyRoutingRecipientsMax) {
    fields.recipients = `Use at most ${createRuleBodyRoutingRecipientsMax} recipients.`
  }
  if (draft.channels !== null && draft.channels.length === 0) fields.channels = 'Pick at least one channel.'
  if (draft.title.trim() === '') fields.title = 'Write a title, e.g. Settlement {{payload.workflowId}} failed.'
  else if (draft.title.length > createRuleBodyPresentationTitleMax) {
    fields.title = `Use at most ${createRuleBodyPresentationTitleMax} characters.`
  }
  if (draft.body.length > createRuleBodyPresentationBodyOneMax) {
    fields.body = `Use at most ${createRuleBodyPresentationBodyOneMax} characters.`
  }
  if (draft.fields.length > createRuleBodyPresentationFieldsMax) {
    fields.fields = `List at most ${createRuleBodyPresentationFieldsMax} fields.`
  }
  const badField = draft.fields.map(fieldPathProblem).find((problem) => problem !== null)
  if (badField !== undefined) fields.fields = badField
  if (draft.dedupFields.length > createRuleBodyDedupFieldsMax) {
    fields.dedupFields = `Use at most ${createRuleBodyDedupFieldsMax} fields.`
  }
  const badDedup = draft.dedupFields.map(fieldPathProblem).find((problem) => problem !== null)
  if (badDedup !== undefined) fields.dedupFields = badDedup
  const window = windowSeconds(draft)
  if (window === null) fields.window = 'Enter a whole number between 1 second and 24 hours.'

  if (!condition.ok || window === null || Object.keys(fields).length > 0) {
    return { ok: false, errors: { fields, nodes, root: null } }
  }
  return {
    ok: true,
    parts: {
      name,
      description: draft.description.trim() === '' ? null : draft.description,
      enabled: draft.enabled,
      schema_ids: draft.schemaIds,
      condition: condition.condition,
      dedup: { fields: draft.dedupFields, window_s: window },
      routing: { recipients: draft.recipients, channels: draft.channels },
      presentation: {
        title: draft.title,
        body: draft.body.trim() === '' ? null : draft.body,
        fields: draft.fields,
        severity: draft.severity,
        colour: draft.colour,
      },
      runbook_id: draft.runbookId,
    },
  }
}

/** `POST /rules` body for valid parts. */
export function toCreate(parts: RuleParts, owner: Owner): RuleCreate {
  return { ...parts, owner }
}

function changed(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) !== JSON.stringify(b)
}

/**
 * `PATCH /rules/{id}` body with only what differs from `saved` (DOMAIN.md §1). `null` clears `description` and
 * `runbook_id` only; elsewhere the field is left out when unchanged.
 */
export function toUpdate(parts: RuleParts, saved: RuleRead): RuleUpdate {
  const update: RuleUpdate = {}
  if (parts.name !== saved.name) update.name = parts.name
  if (parts.description !== saved.description) update.description = parts.description
  if (parts.enabled !== saved.enabled) update.enabled = parts.enabled
  if (changed(parts.schema_ids, saved.schema_ids)) update.schema_ids = parts.schema_ids
  if (changed(parts.condition, saved.condition)) update.condition = parts.condition
  if (changed(parts.dedup, { fields: saved.dedup.fields ?? [], window_s: saved.dedup.window_s })) update.dedup = parts.dedup
  if (changed(parts.routing, { recipients: saved.routing.recipients, channels: saved.routing.channels ?? null })) {
    update.routing = parts.routing
  }
  const presentation = saved.presentation
  if (
    changed(parts.presentation, {
      title: presentation.title,
      body: presentation.body ?? null,
      fields: presentation.fields ?? [],
      severity: presentation.severity,
      colour: presentation.colour,
    })
  ) {
    update.presentation = parts.presentation
  }
  if (parts.runbook_id !== saved.runbook_id) update.runbook_id = parts.runbook_id
  return update
}

const topLevelField = {
  name: 'name',
  description: 'description',
  schema_ids: 'schemaIds',
  runbook_id: 'runbook',
} as const satisfies Partial<Record<keyof RuleCreate, DraftField>>

const presentationField = {
  title: 'title',
  body: 'body',
  fields: 'fields',
  severity: 'severity',
  colour: 'colour',
} as const satisfies Record<string, DraftField>

function lookup<T extends object>(map: T, key: string | number | undefined): T[keyof T] | undefined {
  if (typeof key !== 'string') return undefined
  const entry = Object.entries(map).find(([name]) => name === key)
  return entry?.[1]
}

/** Puts each `422` error (`loc` below `body`) under the builder field or condition node it names; the rest go to `root`. */
export function placeIssues(draft: RuleDraft, issues: readonly BodyIssue[]): DraftErrors {
  const fields: DraftErrors['fields'] = {}
  const nodes: DraftErrors['nodes'] = {}
  const unplaced: string[] = []
  for (const { path, message } of issues) {
    const [head, next] = path
    let field: DraftField | undefined
    if (head === 'condition') {
      const location = locateIssue(draft.condition, path.slice(1))
      if (location !== null) {
        nodes[location.nodeId] = { ...nodes[location.nodeId], [location.part]: message }
        continue
      }
    } else if (head === 'presentation') field = lookup(presentationField, next)
    else if (head === 'routing') field = next === 'channels' ? 'channels' : 'recipients'
    else if (head === 'dedup') field = next === 'window_s' ? 'window' : 'dedupFields'
    else field = lookup(topLevelField, head)
    if (field === undefined) unplaced.push(message)
    else fields[field] = message
  }
  const root =
    unplaced.length > 0 || issues.length === 0
      ? `Couldn't save the rule. ${unplaced[0] ?? 'Check the highlighted fields and try again.'}`
      : null
  return { fields, nodes, root }
}
