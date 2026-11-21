import { ShieldCheck } from 'lucide-react'
import type { Step } from '@/api/generated/model'
import { Badge } from '@/components/ui/badge'
import { approvalSentence, effectiveApproval, guardText, stepActionInfo, stepParameters } from '@/lib/runbooks'
import { TemplateText } from './template-text'

/**
 * A runbook's steps as written, before any run: number, action icon and label, what it does and whether it waits for
 * approval, its parameters with placeholders highlighted, the question it asks and its guard. Read-only; the run
 * states of DESIGN.md §5.3 belong to the alert's `StepList`.
 */
export function ParsedStepList({ steps, label = 'Steps' }: { steps: readonly Step[]; label?: string }) {
  return (
    <ol aria-label={label} className="flex flex-col divide-y">
      {steps.map((step, index) => (
        <ParsedStep key={index} step={step} index={index} steps={steps} />
      ))}
    </ol>
  )
}

function ParsedStep({ step, index, steps }: { step: Step; index: number; steps: readonly Step[] }) {
  const { icon: Icon, label, summary } = stepActionInfo[step.action]
  const parameters = stepParameters(step)
  const { check, if: guard } = step
  return (
    <li className="flex gap-3 py-3 first:pt-0 last:pb-0">
      <span className="mt-0.5 w-5 shrink-0 text-right font-mono text-[13px]/[20px] text-muted-foreground tabular-nums">
        {index + 1}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Icon size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-muted-foreground" />
          <span className="font-medium">{label}</span>
          {effectiveApproval(step) === 'required' && (
            <Badge className="bg-accent text-primary">
              <ShieldCheck strokeWidth={1.75} aria-hidden />
              Needs approval
            </Badge>
          )}
        </div>
        <p className="text-[12px]/[16px] text-muted-foreground">
          {summary} {approvalSentence(step)}
        </p>
        {step.action === 'manual' && <TemplateText text={step.text} className="whitespace-pre-wrap" />}
        {parameters.length > 0 && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            {parameters.map((parameter) => (
              <div key={parameter.label} className="contents">
                <dt className="text-[12px]/[20px] text-muted-foreground">{parameter.label}</dt>
                <dd className="min-w-0 font-mono text-[13px]/[20px] font-[450]">
                  {parameter.templated ? <TemplateText text={parameter.value} /> : parameter.value}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {check !== undefined && check !== null && <p className="text-[13px]/[20px]">Question: {check}</p>}
        {guard !== undefined && guard !== null && <p className="text-[13px]/[20px] text-muted-foreground">{guardText(guard, steps)}</p>}
      </div>
    </li>
  )
}
