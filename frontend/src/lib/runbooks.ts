import {
  ArrowUpRight,
  Globe,
  Hourglass,
  ListTodo,
  Power,
  RotateCcw,
  Ticket,
  Webhook,
  type LucideIcon,
} from 'lucide-react'
import type { CompareOp, Condition, RunbookFormat, Scalar, Step, StepGuard } from '@/api/generated/model'

/** Every step action the contract knows (SPEC §11.2). */
export type StepAction = Step['action']

/** Whether a step waits for a team lead before it runs (`RUN-4`). */
export type Approval = 'none' | 'required'

/**
 * Default approval per action, copied from SPEC §11.2 because the contract does not expose it (ADR-0062).
 * Read-only actions and human steps run on their own; actions that change a running system wait for a lead.
 * `retry_workflow` is `none`: the brief's YAML sets `approval: none` on it, which stricter-only rules (ADR-0019)
 * allow only when the default is already `none`.
 */
export const defaultApproval = {
  http_get: 'none',
  retry_workflow: 'none',
  restart_service: 'required',
  call_webhook: 'required',
  open_ticket: 'none',
  escalate: 'required',
  wait: 'none',
  manual: 'none',
} as const satisfies Record<StepAction, Approval>

/** Icon, label and what the action does, in plain words for non-engineers (`UI-6`). */
export interface StepActionInfo {
  icon: LucideIcon
  /** Sentence-case name, e.g. "Restart service". */
  label: string
  /** What happens when the step runs, one sentence. */
  summary: string
}

export const stepActionInfo = {
  http_get: { icon: Globe, label: 'Check a URL', summary: 'Opens the address and shows the answer on the alert.' },
  retry_workflow: { icon: RotateCcw, label: 'Retry workflow', summary: 'Starts the failed workflow again.' },
  restart_service: { icon: Power, label: 'Restart service', summary: 'Restarts the named service.' },
  call_webhook: { icon: Webhook, label: 'Call webhook', summary: 'Sends a request to the address.' },
  open_ticket: { icon: Ticket, label: 'Open ticket', summary: 'Opens a ticket with this title.' },
  escalate: { icon: ArrowUpRight, label: 'Escalate', summary: 'Notifies another team and adds it to the alert.' },
  wait: { icon: Hourglass, label: 'Wait', summary: 'Pauses before the next step.' },
  manual: { icon: ListTodo, label: 'Manual step', summary: 'A person does this and ticks it off.' },
} as const satisfies Record<StepAction, StepActionInfo>

/**
 * The approval a step runs with: the runbook may make an action stricter than its default, never looser (ADR-0019),
 * so a `none` on an action that defaults to `required` still needs approval.
 */
export function effectiveApproval(step: Step): Approval {
  return step.approval === 'required' || defaultApproval[step.action] === 'required' ? 'required' : 'none'
}

/** One sentence on whether the step waits for a person, for the step's description. */
export function approvalSentence(step: Step): string {
  return effectiveApproval(step) === 'required' ? 'A team lead approves it before it runs.' : 'Runs without approval.'
}

/** One parameter of a step, shown under its label. */
export interface StepParameter {
  label: string
  value: string
  /** The value may hold `{{field.path}}` placeholders, filled from the event when the step runs. */
  templated: boolean
}

/** The values a step runs with, in the order a person reads them; `manual` shows its text instead. */
export function stepParameters(step: Step): StepParameter[] {
  switch (step.action) {
    case 'http_get':
      return [{ label: 'URL', value: step.url, templated: true }]
    case 'retry_workflow':
      return [{ label: 'Workflow', value: step.workflowId, templated: true }]
    case 'restart_service':
      return [{ label: 'Service', value: step.service, templated: true }]
    case 'call_webhook':
      return [
        { label: 'Method', value: step.method ?? 'POST', templated: false },
        { label: 'URL', value: step.url, templated: true },
      ]
    case 'open_ticket':
      return [{ label: 'Title', value: step.title, templated: true }]
    case 'escalate':
      return [{ label: 'Team', value: step.team, templated: false }]
    case 'wait':
      return [{ label: 'For', value: duration(step.seconds), templated: false }]
    case 'manual':
      return []
    default:
      return step satisfies never
  }
}

/** "90 seconds", "2 minutes", "1 hour 30 minutes"; seconds stay exact when they are not whole minutes. */
export function duration(seconds: number): string {
  if (seconds % 60 !== 0) return plural(seconds, 'second')
  const hours = Math.floor(seconds / 3600)
  const minutes = (seconds % 3600) / 60
  return [hours > 0 ? plural(hours, 'hour') : '', minutes > 0 ? plural(minutes, 'minute') : '']
    .filter((part) => part !== '')
    .join(' ')
}

function plural(count: number, unit: string): string {
  return `${count} ${unit}${count === 1 ? '' : 's'}`
}

function times(count: number): string {
  if (count === 1) return 'once'
  if (count === 2) return 'twice'
  return `${count} times`
}

/**
 * The step's guard as a sentence. A parsed guard names the step it waits on (1-based, with its label when the step
 * is in `steps`); free text that could not be parsed is a yes / no question a person answers (SPEC §11.4).
 */
export function guardText(guard: StepGuard | string, steps: readonly Step[]): string {
  if (typeof guard === 'string') return `A person answers first: "${guard}?"`
  const target = steps[guard.step]
  const name = target === undefined ? '' : ` (${stepActionInfo[target.action].label})`
  return `Only after step ${guard.step + 1}${name} has failed ${times(guard.failures_gte)}.`
}

/** Steps of `steps` that wait for a team lead. */
export function approvalCount(steps: readonly Step[]): number {
  return steps.filter((step) => effectiveApproval(step) === 'required').length
}

/** Label and helper text per input format (SPEC §11.1). */
export const runbookFormatInfo = {
  structured: { label: 'YAML', hint: 'Structured steps. Each step becomes an action; matches: sets when it applies.' },
  markdown: { label: 'Markdown', hint: 'Each numbered or bulleted item becomes a step a person ticks off.' },
  text: { label: 'Free text', hint: 'Kept as written and shown as one step a person follows.' },
  link: { label: 'Link', hint: 'A link to a wiki or Confluence page, shown as one step: open the runbook.' },
} as const satisfies Record<RunbookFormat, { label: string; hint: string }>

const compareSymbol = {
  eq: '=',
  ne: '≠',
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
} as const satisfies Record<CompareOp, string>

function scalar(value: Scalar): string {
  return value === null ? 'null' : String(value)
}

function nested(condition: Condition): string {
  const text = describeCondition(condition)
  return condition.op === 'and' || condition.op === 'or' ? `(${text})` : text
}

/** A condition as one line, e.g. `type = WORKFLOW_FAILED and error.code = TIMEOUT`. */
export function describeCondition(condition: Condition): string {
  switch (condition.op) {
    case 'and':
      return condition.args.map(nested).join(' and ')
    case 'or':
      return condition.args.map(nested).join(' or ')
    case 'not':
      return `not ${nested(condition.arg)}`
    case 'eq':
    case 'ne':
    case 'gt':
    case 'gte':
    case 'lt':
    case 'lte':
      return `${condition.field} ${compareSymbol[condition.op]} ${scalar(condition.value)}`
    case 'in':
      return `${condition.field} is one of ${condition.value.map(scalar).join(', ')}`
    case 'not_in':
      return `${condition.field} is none of ${condition.value.map(scalar).join(', ')}`
    case 'contains':
      return `${condition.field} contains ${scalar(condition.value)}`
    case 'glob':
      return `${condition.field} matches ${condition.value}`
    case 'exists':
      return `${condition.field} is set`
    default:
      return condition satisfies never
  }
}

/** Splits text into plain parts and `{{…}}` placeholders, in order, so placeholders can be highlighted. */
export function templateParts(text: string): { text: string; placeholder: boolean }[] {
  return text
    .split(/(\{\{[^{}]*\}\})/)
    .filter((part) => part !== '')
    .map((part) => ({ text: part, placeholder: /^\{\{[^{}]*\}\}$/.test(part) }))
}
