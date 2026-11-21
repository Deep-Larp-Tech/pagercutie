import { useEffect, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { CircleCheck, CircleSlash, LoaderCircle } from 'lucide-react'
import type { RuleTestRequest, Severity } from '@/api/generated/model'
import { testRule } from '@/api/generated/rules/rules'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { unexpectedStatusMessage } from '@/lib/api'
import type { ConditionResult } from '@/lib/rule-condition'
import { severityLabel } from '@/lib/severity'
import { bodyIssues } from '@/lib/validation-errors'
import { parseSample, type SampleEvent } from '@/lib/rule-sample'
import { BODY_UNREADABLE, OFFLINE } from './messages'

/** How long typing must pause before the panel asks the API again (ms). */
const TEST_DEBOUNCE_MS = 400

/** Most severe first, as people read the list. */
const SEVERITIES: readonly Severity[] = ['critical', 'error', 'warn', 'info', 'debug']
const severityItems = SEVERITIES.map((value) => ({ value, label: severityLabel[value] }))

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

/** Props for `RuleTestPanel`. */
export interface RuleTestPanelProps {
  sample: SampleEvent
  onSample: (sample: SampleEvent) => void
  /** The draft's condition, or the problems that stop it from being built. */
  condition: ConditionResult
  /** First selected event schema, sent as the event's `schema_id`. */
  schemaId: string | null
  readOnly: boolean
}

type TestOutcome =
  | { kind: 'idle'; message: string }
  | { kind: 'running' }
  | { kind: 'matched'; title: string | null }
  | { kind: 'missed' }
  | { kind: 'failed'; message: string }

/**
 * "Does it match?": a sample event the author edits, checked live against the draft's condition with
 * `POST /rules/test`, which saves nothing.
 */
export function RuleTestPanel({ sample, onSample, condition, schemaId, readOnly }: RuleTestPanelProps) {
  const empty = sample.payload.trim() === ''
  const parsed = empty ? null : parseSample(sample.payload)
  const request: RuleTestRequest | null =
    condition.ok && parsed?.ok === true
      ? { condition: condition.condition, payload: parsed.payload, source: sample.source, severity: sample.severity, schema_id: schemaId }
      : null
  const key = useDebounced(request === null ? null : JSON.stringify(request), TEST_DEBOUNCE_MS)
  const query = useQuery({
    queryKey: ['rule-test', key],
    queryFn: async ({ signal }) => {
      if (request === null) throw new Error('No rule to test')
      return testRule(request, { signal })
    },
    enabled: request !== null && key === JSON.stringify(request),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })

  let outcome: TestOutcome
  if (!condition.ok) outcome = { kind: 'idle', message: 'Finish the condition above to test it.' }
  else if (parsed === null) outcome = { kind: 'idle', message: 'Paste a sample event to test the rule.' }
  else if (!parsed.ok) outcome = { kind: 'idle', message: 'Fix the sample to test the rule.' }
  else if (query.isError) outcome = { kind: 'failed', message: OFFLINE }
  else if (query.data === undefined || query.isPlaceholderData) outcome = { kind: 'running' }
  else {
    const response = query.data
    switch (response.status) {
      case 200:
        outcome = response.data.matched ? { kind: 'matched', title: response.data.title ?? null } : { kind: 'missed' }
        break
      case 400:
        outcome = { kind: 'failed', message: BODY_UNREADABLE }
        break
      case 401:
        outcome = { kind: 'idle', message: '' }
        break
      case 422:
        outcome = {
          kind: 'failed',
          message: `Couldn't test the rule. ${bodyIssues(response.data)[0]?.message ?? 'Check the condition and the sample.'}`,
        }
        break
      default:
        outcome = { kind: 'failed', message: unexpectedStatusMessage(response) }
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg border p-4">
      <div className="flex flex-col gap-1">
        <h3 className="font-semibold">Test with a sample event</h3>
        <p className="text-[12px]/[16px] text-muted-foreground">
          Paste an event your source sends. Nothing is saved or sent to anyone.
        </p>
      </div>
      <Field invalid={parsed?.ok === false}>
        <FieldLabel>Sample event payload (JSON)</FieldLabel>
        <Textarea
          rows={6}
          spellCheck={false}
          className="font-mono text-[13px]/[20px]"
          value={sample.payload}
          readOnly={readOnly}
          aria-invalid={parsed?.ok === false || undefined}
          onChange={(event) => onSample({ ...sample, payload: event.target.value })}
        />
        {parsed?.ok === false ? (
          <FieldError>{parsed.message}</FieldError>
        ) : (
          <FieldDescription>The body only; source and severity are set below.</FieldDescription>
        )}
      </Field>
      <div className="flex flex-wrap gap-4">
        <Field className="w-56">
          <FieldLabel>Event source</FieldLabel>
          <Input
            value={sample.source}
            readOnly={readOnly}
            className="font-mono text-[13px]"
            onChange={(event) => onSample({ ...sample, source: event.target.value })}
          />
        </Field>
        <Field className="w-auto">
          <FieldLabel>Event severity</FieldLabel>
          <Select items={severityItems} value={sample.severity} onValueChange={(severity) => severity !== null && onSample({ ...sample, severity })}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {severityItems.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>
      <TestResult outcome={outcome} />
    </div>
  )
}

function TestResult({ outcome }: { outcome: TestOutcome }) {
  switch (outcome.kind) {
    case 'idle':
      return (
        <p role="status" className="text-muted-foreground">
          {outcome.message}
        </p>
      )
    case 'running':
      return (
        <p role="status" className="flex items-center gap-2 text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" strokeWidth={1.75} aria-hidden />
          Testing…
        </p>
      )
    case 'matched':
      return (
        <div role="status" className="flex flex-col gap-1">
          <p className="flex items-center gap-2 font-medium">
            <CircleCheck className="size-4 text-alert-green" strokeWidth={1.75} aria-hidden />
            Matches: this event would raise an alert.
          </p>
          {outcome.title !== null && <p className="text-muted-foreground">Title: {outcome.title}</p>}
        </div>
      )
    case 'missed':
      return (
        <p role="status" className="flex items-center gap-2 font-medium">
          <CircleSlash className="size-4 text-muted-foreground" strokeWidth={1.75} aria-hidden />
          Doesn't match: this event would not raise an alert.
        </p>
      )
    case 'failed':
      return (
        <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
          {outcome.message}
        </p>
      )
    default:
      return outcome satisfies never
  }
}
