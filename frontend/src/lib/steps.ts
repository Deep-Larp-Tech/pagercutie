import {
  Globe,
  Hand,
  Hourglass,
  RotateCcw,
  Power,
  Siren,
  Ticket,
  Webhook,
  type LucideIcon,
} from 'lucide-react'
import type { Step, StepDecisionKind, StepGuard, StepStatus } from '@/api/generated/model'
import { renderTemplate } from './templates'

/** A runbook step's action type (SPEC §11.2). */
export type StepAction = Step['action']

/** Icon, label and a one-line description of what each action does, for non-engineers (`UI-6`). */
export const stepActionInfo = {
  http_get: { icon: Globe, label: 'Check a URL', description: 'Sends a GET request and shows the answer.' },
  call_webhook: { icon: Webhook, label: 'Call a webhook', description: 'Sends a request to a URL.' },
  retry_workflow: {
    icon: RotateCcw,
    label: 'Retry the workflow',
    description: 'Asks the workflow engine to run the workflow again.',
  },
  restart_service: { icon: Power, label: 'Restart a service', description: 'Restarts the service.' },
  open_ticket: { icon: Ticket, label: 'Open a ticket', description: 'Creates a ticket with this title.' },
  escalate: {
    icon: Siren,
    label: 'Escalate to another team',
    description: "Notifies another team and adds the alert to their feed.",
  },
  wait: { icon: Hourglass, label: 'Wait', description: 'Pauses before the next step.' },
  manual: { icon: Hand, label: 'Do it by hand', description: 'Someone follows the instruction and marks it done.' },
} as const satisfies Record<StepAction, { icon: LucideIcon; label: string; description: string }>

/** Words for each step status (DESIGN.md §5.3); the indicator adds the shape. */
export const stepStatusLabel = {
  pending: 'Waiting',
  awaiting_approval: 'Needs approval',
  awaiting_answer: 'Needs an answer',
  awaiting_manual: 'To do by hand',
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
  skipped: 'Skipped',
} as const satisfies Record<StepStatus, string>

/** Who may make a decision: a team lead (`RUN-4`), or a member or lead (DOMAIN.md §4). */
export type DecisionRole = 'approver' | 'responder'

/** The decisions a step in each status accepts (DOMAIN.md §6) and who may make them; `null` when none. */
export const stepDecisions = {
  pending: null,
  awaiting_approval: { role: 'approver', kinds: ['approve', 'reject'] },
  awaiting_answer: { role: 'responder', kinds: ['yes', 'no'] },
  awaiting_manual: { role: 'responder', kinds: ['done'] },
  running: null,
  succeeded: null,
  failed: null,
  skipped: null,
} as const satisfies Record<StepStatus, { role: DecisionRole; kinds: readonly StepDecisionKind[] } | null>

/** The status a step moves to right after each decision, shown until the API answers (optimistic). */
export const statusAfterDecision = {
  approve: 'running',
  reject: 'skipped',
  yes: 'pending',
  no: 'skipped',
  done: 'succeeded',
} as const satisfies Record<StepDecisionKind, StepStatus>

/** One parameter of a step, shown under its label. */
export interface StepParameter {
  label: string
  /** The value, with `{{…}}` placeholders filled when a payload was given. */
  value: string
  /** The value may hold `{{field.path}}` placeholders, filled from the event when the step runs. */
  templated: boolean
}

const durationUnits = [
  ['hour', 3600],
  ['minute', 60],
  ['second', 1],
] as const satisfies readonly (readonly [string, number])[]

/** `seconds` in words: "90 seconds" as "1 minute 30 seconds". */
export function formatDuration(seconds: number): string {
  let rest = seconds
  const parts: string[] = []
  for (const [unit, length] of durationUnits) {
    const count = Math.floor(rest / length)
    rest -= count * length
    if (count > 0) parts.push(`${count} ${unit}${count === 1 ? '' : 's'}`)
  }
  return parts.length === 0 ? '0 seconds' : parts.join(' ')
}

/**
 * The values `step` runs with, in the order a person reads them; `manual` shows its text instead. With `payload` (the
 * alert's first event) the `{{…}}` placeholders are filled (`RUN-2`); without it they stay as written, for previews.
 */
export function stepParameters(step: Step, payload?: Record<string, unknown>): StepParameter[] {
  const templated = (label: string, template: string): StepParameter => ({
    label,
    value: payload === undefined ? template : renderTemplate(template, payload),
    templated: true,
  })
  const plain = (label: string, value: string): StepParameter => ({ label, value, templated: false })
  switch (step.action) {
    case 'http_get':
      return [templated('URL', step.url)]
    case 'call_webhook':
      return [plain('Method', step.method ?? 'POST'), templated('URL', step.url)]
    case 'retry_workflow':
      return [templated('Workflow', step.workflowId)]
    case 'restart_service':
      return [templated('Service', step.service)]
    case 'open_ticket':
      return [templated('Title', step.title)]
    case 'escalate':
      return [plain('Team', step.team)]
    case 'wait':
      return [plain('Duration', formatDuration(step.seconds))]
    case 'manual':
      return []
    default:
      return step satisfies never
  }
}

/** One sentence saying what `step` does when it runs, with values filled in; the approval dialog names it. */
export function stepSummary(step: Step, payload: Record<string, unknown>): string {
  const fill = (template: string) => renderTemplate(template, payload)
  switch (step.action) {
    case 'http_get':
      return `Sends a GET request to ${fill(step.url)}.`
    case 'call_webhook':
      return `Sends a ${step.method ?? 'POST'} request to ${fill(step.url)}.`
    case 'retry_workflow':
      return `Retries workflow ${fill(step.workflowId)}.`
    case 'restart_service':
      return `Restarts ${fill(step.service)}.`
    case 'open_ticket':
      return `Opens a ticket titled "${fill(step.title)}".`
    case 'escalate':
      return `Escalates the alert to team ${step.team}, whose people get notified.`
    case 'wait':
      return `Waits ${formatDuration(step.seconds)}.`
    case 'manual':
      return fill(step.text)
    default:
      return step satisfies never
  }
}

function times(count: number): string {
  if (count === 1) return 'once'
  if (count === 2) return 'twice'
  return `${count} times`
}

/**
 * A step's guard as a sentence, numbering steps from 1 as the lists do: "Runs when step 2 (Retry the workflow) has
 * failed twice or more." The step's label shows when it is in `steps`. Free text the parser could not read is a yes
 * / no question a person answers (SPEC §11.4).
 */
export function guardText(guard: StepGuard | string, steps: readonly Step[] = []): string {
  if (typeof guard === 'string') return `A person answers first: "${guard}?"`
  const target = steps[guard.step]
  const name = target === undefined ? '' : ` (${stepActionInfo[target.action].label})`
  return `Runs when step ${guard.step + 1}${name} has failed ${times(guard.failures_gte)} or more.`
}

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

/** Steps of `steps` that wait for a team lead. */
export function approvalCount(steps: readonly Step[]): number {
  return steps.filter((step) => effectiveApproval(step) === 'required').length
}
