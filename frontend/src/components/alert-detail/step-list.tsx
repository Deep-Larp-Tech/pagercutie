import { useState } from 'react'
import { Check, LoaderCircle } from 'lucide-react'
import type { AlertRead, Step, StepDecisionKind, StepRunRead, StepStatus } from '@/api/generated/model'
import { RelativeTime } from '@/components/alerts/relative-time'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { usePersonName } from '@/hooks/use-person-name'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'
import {
  guardText,
  stepActionInfo,
  stepDecisions,
  stepParameters,
  stepStatusLabel,
  stepSummary,
  type DecisionRole,
} from '@/lib/steps'
import { cn } from '@/lib/utils'
import { PersonNameText } from './person-name'
import { useStepDecision } from './use-step-decision'

const label = 'flex items-center gap-1.5 text-[12px]/[16px] font-medium'

/** Step status by shape and words (DESIGN.md §5.3); violet marks a step that waits on a person. */
export function StepStatusIndicator({ status }: { status: StepStatus }) {
  const text = stepStatusLabel[status]
  switch (status) {
    case 'pending':
      return (
        <span className={cn(label, 'text-muted-foreground')}>
          <span className="size-2.5 rounded-full border-2 border-alert-grey" aria-hidden />
          {text}
        </span>
      )
    case 'awaiting_approval':
      return (
        <span className={cn(label, 'text-primary')}>
          <span className="relative flex size-2.5" aria-hidden>
            <span className="absolute inline-flex size-full animate-live-ping rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex size-2.5 rounded-full bg-primary" />
          </span>
          {text}
        </span>
      )
    case 'awaiting_answer':
    case 'awaiting_manual':
      return (
        <span className={cn(label, 'text-primary')}>
          <span className="size-2.5 rounded-full border-2 border-primary" aria-hidden />
          {text}
        </span>
      )
    case 'running':
      return (
        <span className={cn(label, 'text-alert-blue-text')}>
          <LoaderCircle size={14} strokeWidth={1.75} className="animate-spin" aria-hidden />
          {text}
        </span>
      )
    case 'succeeded':
      return (
        <span className={cn(label, 'text-alert-green-text')}>
          <Check size={14} strokeWidth={1.75} aria-hidden />
          {text}
        </span>
      )
    case 'failed':
      return (
        <span className={cn(label, 'text-alert-red-text')}>
          <span className="size-2.5 rounded-full bg-alert-red" aria-hidden />
          {text}
        </span>
      )
    case 'skipped':
      return (
        <span className={cn(label, 'text-muted-foreground')}>
          <span className="size-2.5 rounded-full bg-muted-foreground/50" aria-hidden />
          {text}
        </span>
      )
    default:
      return status satisfies never
  }
}

/** Button label for each decision (DESIGN.md §10: one label per action). */
const decisionLabel = {
  approve: 'Approve step',
  reject: 'Reject step',
  yes: 'Yes',
  no: 'No',
  done: 'Mark as done',
} as const satisfies Record<StepDecisionKind, string>

/** What someone who may not decide sees instead of the buttons. */
const waitingOn = {
  approver: 'Waiting for a team lead to approve.',
  responder: 'Waiting for a team member.',
} as const satisfies Record<DecisionRole, string>

function mayDecide(role: DecisionRole, mayRespond: boolean, mayApprove: boolean): boolean {
  switch (role) {
    case 'approver':
      return mayApprove
    case 'responder':
      return mayRespond
    default:
      return role satisfies never
  }
}

function StepDecisionControls({ alert, step, mayRespond, mayApprove }: StepRowProps) {
  const { decide, pending, error } = useStepDecision(alert.id, step)
  const [confirming, setConfirming] = useState(false)
  const options = stepDecisions[step.status]
  if (options === null) return null
  if (!mayDecide(options.role, mayRespond, mayApprove)) {
    return <p className="text-[12px]/[16px] text-muted-foreground">{waitingOn[options.role]}</p>
  }
  const { label: actionLabel } = stepActionInfo[step.step.action]
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        {options.kinds.map((kind, position) => (
          <Button
            key={kind}
            size="sm"
            variant={position === 0 ? 'primary' : 'secondary'}
            disabled={pending}
            onClick={() => (kind === 'approve' ? setConfirming(true) : void decide(kind))}
          >
            {decisionLabel[kind]}
          </Button>
        ))}
      </div>
      {error !== null && !confirming && (
        <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
          {error}
        </p>
      )}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Approve step ${step.index + 1}: ${actionLabel}?`}
        description={`${stepSummary(step.step, alert.payload)} It runs as soon as you approve.`}
        confirmLabel="Approve step"
        confirmVariant="primary"
        pendingLabel="Approving…"
        pending={pending}
        error={error}
        onConfirm={() =>
          void decide('approve').then((accepted) => {
            if (accepted) setConfirming(false)
          })
        }
      />
    </div>
  )
}

interface StepRowProps {
  alert: AlertRead
  step: StepRunRead
  mayRespond: boolean
  mayApprove: boolean
  /** Every step of the run in `index` order, so a guard can name the step it waits on. */
  runbookSteps: readonly Step[]
}

function StepRow(props: StepRowProps) {
  const { alert, step } = props
  const me = useMe()
  const personName = usePersonName()
  const { icon: Icon, label: actionLabel, description } = stepActionInfo[step.step.action]
  const parameters = stepParameters(step.step, alert.payload)
  const guard = step.step.if
  const skipped = step.status === 'skipped'
  const waiting = stepDecisions[step.status] !== null
  return (
    <li
      aria-label={`Step ${step.index + 1}: ${actionLabel}`}
      className={cn(
        'grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 rounded-lg border p-4',
        waiting ? 'border-primary/40 bg-card shadow-card' : 'bg-card',
      )}
    >
      <span
        className={cn(
          'flex size-8 items-center justify-center rounded-full bg-muted',
          waiting ? 'text-primary' : 'text-muted-foreground',
        )}
      >
        <Icon size={16} strokeWidth={1.75} aria-hidden />
      </span>
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-mono text-[13px]/[20px] text-muted-foreground tabular-nums">{step.index + 1}</span>
          <h3 className={cn('text-[15px]/[22px] font-[560]', skipped && 'text-muted-foreground line-through')}>
            {actionLabel}
          </h3>
          <StepStatusIndicator status={step.status} />
          {step.step.approval === 'required' && step.status !== 'awaiting_approval' && (
            <span className="text-[12px]/[16px] text-muted-foreground">Needs a lead's approval</span>
          )}
        </div>
        <p className="text-muted-foreground">{description}</p>

        {step.step.check !== undefined && step.step.check !== null && <p className="font-medium">{step.step.check}</p>}
        {step.step.action === 'manual' && (
          <p className="whitespace-pre-line">{stepSummary(step.step, alert.payload)}</p>
        )}
        {typeof guard === 'string' && (
          <p className={cn(step.status === 'awaiting_answer' && 'font-medium text-primary')}>{guard}?</p>
        )}
        {typeof guard === 'object' && guard !== null && (
          <p className="text-muted-foreground">{guardText(guard, props.runbookSteps)}</p>
        )}

        {parameters.length > 0 && (
          <dl className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-x-3 font-mono text-[13px]/[20px] font-[450]">
            {parameters.map((parameter) => (
              <div key={parameter.label} className="contents">
                <dt className="text-muted-foreground">{parameter.label}</dt>
                <dd className="break-all">{parameter.value}</dd>
              </div>
            ))}
          </dl>
        )}

        {step.result !== null && (
          <p
            className={cn(
              'font-mono text-[13px]/[20px] font-[450] break-words',
              step.status === 'failed' ? 'text-alert-red-text' : 'text-foreground',
            )}
          >
            {step.result}
          </p>
        )}

        {(step.attempts > 0 || step.failures > 0 || step.decided_by !== null) && (
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]/[16px] text-muted-foreground">
            {step.attempts > 0 && (
              <span className="tabular-nums">
                {step.attempts} {step.attempts === 1 ? 'attempt' : 'attempts'}
              </span>
            )}
            {step.failures > 0 && (
              <span className="tabular-nums">
                {step.failures} {step.failures === 1 ? 'failure' : 'failures'}
              </span>
            )}
            {step.decided_by !== null && (
              <span className="flex items-center gap-1">
                Decided by
                <span className="font-medium text-foreground">
                  <PersonNameText person={personName(step.decided_by)} />
                </span>
                {step.decided_at !== null && (
                  <RelativeTime value={step.decided_at} timeZone={me.user.timezone} />
                )}
              </span>
            )}
          </p>
        )}

        <StepDecisionControls {...props} />
      </div>
    </li>
  )
}

/** Props for `StepList`. */
export interface StepListProps {
  alert: AlertRead
  /** The run's steps; shown in `index` order. */
  steps: readonly StepRunRead[]
}

/**
 * A runbook run's steps in order (DESIGN.md §5.3, `RUN-2`–`RUN-5`): action, parameters filled from the event, status,
 * attempts, result and who decided. Approve and Reject show for leads (`RUN-4`); Yes, No and Mark as done for members
 * and leads; everyone else sees who the step waits for.
 */
export function StepList({ alert, steps }: StepListProps) {
  const me = useMe()
  const mayRespond = alert.team_id === null || can(me, 'alert.respond', alert)
  const mayApprove = can(me, 'step.approve', alert)
  const ordered = steps.toSorted((a, b) => a.index - b.index)
  const runbookSteps = ordered.map((run) => run.step)
  return (
    <ol className="flex flex-col gap-3" aria-label="Runbook steps">
      {ordered.map((step) => (
        <StepRow
          key={step.index}
          alert={alert}
          step={step}
          mayRespond={mayRespond}
          mayApprove={mayApprove}
          runbookSteps={runbookSteps}
        />
      ))}
    </ol>
  )
}
