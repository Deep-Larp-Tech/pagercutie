import { TriangleAlert } from 'lucide-react'
import type { Condition, RunbookParseResult } from '@/api/generated/model'
import { Skeleton } from '@/components/ui/skeleton'
import { describeCondition } from '@/lib/runbooks'
import { ParsedStepList } from './parsed-step-list'
import type { ParsePreviewState } from './use-parse-preview'

/** The preview panel next to the runbook text: parsed steps, warnings and the condition from `matches:`. */
export function ParsePreview({ state }: { state: ParsePreviewState }) {
  const updating = 'updating' in state && state.updating
  return (
    <section aria-labelledby="parse-preview-title" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id="parse-preview-title" className="text-[18px]/[26px] font-semibold tracking-[-0.01em]">
            Preview
          </h2>
          <span role="status" className="text-[12px]/[16px] text-muted-foreground">
            {updating ? 'Updating preview…' : ''}
          </span>
        </div>
        <p className="text-muted-foreground">The steps an alert shows when this runbook applies.</p>
      </div>
      <PreviewBody state={state} />
    </section>
  )
}

function PreviewBody({ state }: { state: ParsePreviewState }) {
  switch (state.kind) {
    case 'empty':
      return <p className="text-muted-foreground">Paste a runbook or insert an example to see its steps.</p>
    case 'loading':
      return (
        <div className="flex flex-col gap-3" data-testid="preview-skeleton">
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-12 w-full" />
          ))}
        </div>
      )
    case 'parsed':
      return <ParsedRunbook result={state.result} />
    case 'invalid':
      return (
        <div role="alert" className="flex flex-col gap-1 rounded-lg border border-alert-red/40 px-3 py-2.5">
          <p className="font-medium text-alert-red-text">Couldn't read this runbook</p>
          <ul className="list-disc pl-5 text-[13px]/[20px] text-alert-red-text">
            {state.messages.map((message, index) => (
              <li key={index}>{message}</li>
            ))}
          </ul>
        </div>
      )
    case 'failed':
      return (
        <p role="alert" className="text-muted-foreground">
          {state.message}
        </p>
      )
    default:
      return state satisfies never
  }
}

/** Steps, warnings and condition of a parse result or a saved runbook. */
export function ParsedRunbook({ result }: { result: RunbookParseResult }) {
  return (
    <div className="flex flex-col gap-5">
      {result.warnings.length > 0 && (
        <div className="flex gap-2 rounded-lg border px-3 py-2.5" data-testid="parse-warnings">
          <TriangleAlert size={16} strokeWidth={1.75} aria-hidden className="mt-0.5 shrink-0 text-muted-foreground" />
          <div className="flex flex-col gap-1">
            <p className="font-medium">Kept as steps for a person</p>
            <ul className="flex flex-col gap-0.5 text-[13px]/[20px] text-muted-foreground">
              {result.warnings.map((warning, index) => (
                <li key={index}>{warning}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {result.steps.length === 0 ? (
        <p className="text-muted-foreground">No steps found in this text.</p>
      ) : (
        <ParsedStepList steps={result.steps} label="Parsed steps" />
      )}
      <AttachCondition attach={result.attach} />
    </div>
  )
}

/**
 * When the runbook applies (`attach`), read-only. YAML sets it with `matches:`; the editor sends no condition, so the
 * server keeps what the text says.
 */
export function AttachCondition({ attach }: { attach: Condition | null }) {
  return (
    <div className="flex flex-col gap-1.5">
      <h3 className="text-[15px]/[22px] font-[560]">Applies when</h3>
      {attach === null ? (
        <p className="text-muted-foreground">
          No condition in the text. Rules that name this runbook show it on their alerts.
        </p>
      ) : (
        <>
          <p className="font-mono text-[13px]/[20px] font-[450]">{describeCondition(attach)}</p>
          <details className="text-[12px]/[16px] text-muted-foreground">
            <summary className="w-fit cursor-pointer select-none">Show as JSON</summary>
            <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-3 font-mono text-[13px]/[20px] text-foreground">
              {JSON.stringify(attach, null, 2)}
            </pre>
          </details>
          <p className="text-[12px]/[16px] text-muted-foreground">
            Set by the YAML's matches: block. Rules that name this runbook show it too.
          </p>
        </>
      )}
    </div>
  )
}
