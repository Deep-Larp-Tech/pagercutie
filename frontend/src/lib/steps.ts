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

/** One parameter of a step as shown on the alert: its label and the value filled from the event. */
export interface StepParameter {
  label: string
  value: string
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

/** The parameters of `step` with their `{{…}}` placeholders filled from the alert's first event (`RUN-2`). */
export function stepParameters(step: Step, payload: Record<string, unknown>): StepParameter[] {
  const fill = (template: string) => renderTemplate(template, payload)
  switch (step.action) {
    case 'http_get':
      return [{ label: 'URL', value: fill(step.url) }]
    case 'call_webhook':
      return [
        { label: 'Method', value: step.method ?? 'POST' },
        { label: 'URL', value: fill(step.url) },
      ]
    case 'retry_workflow':
      return [{ label: 'Workflow', value: fill(step.workflowId) }]
    case 'restart_service':
      return [{ label: 'Service', value: fill(step.service) }]
    case 'open_ticket':
      return [{ label: 'Title', value: fill(step.title) }]
    case 'escalate':
      return [{ label: 'Team', value: step.team }]
    case 'wait':
      return [{ label: 'Duration', value: formatDuration(step.seconds) }]
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

/** A structured guard in words, numbering steps from 1 as the list does: "Runs when step 2 has failed 2 times or more." */
export function guardSentence({ step, failures_gte }: StepGuard): string {
  const times = failures_gte === 1 ? 'once' : `${failures_gte} times`
  return `Runs when step ${step + 1} has failed ${times} or more.`
}
