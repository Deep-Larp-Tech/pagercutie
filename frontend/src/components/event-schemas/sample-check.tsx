import { useState } from 'react'
import { CircleCheck, CircleX } from 'lucide-react'
import { useValidateEvent } from '@/api/generated/event-schemas/event-schemas'
import type { SchemaValidateResult } from '@/api/generated/model'
import { Button } from '@/components/ui/button'
import { unexpectedStatusMessage } from '@/lib/api'
import { describeParseError, isJsonObject, parseJson } from '@/lib/json-text'
import { OFFLINE } from '@/lib/pagination'
import { bodyIssues } from '@/lib/validation-errors'
import { JsonEditor } from './json-editor'

const SAMPLE_START = '{\n  \n}'

/** Shown when the sample parses but is not a JSON object. */
const NOT_AN_OBJECT = 'An event payload is a JSON object, wrapped in { }.'

/** What the panel shows under the button. */
type CheckState =
  | { kind: 'idle' }
  | { kind: 'result'; result: SchemaValidateResult }
  /** The check could not run; the message says why. */
  | { kind: 'failed'; message: string }

/** Props for `SampleCheck`. */
export interface SampleCheckProps {
  /** The event schema to check against. */
  schemaId: string
}

/**
 * "Check a sample": a JSON payload checked against the schema with `POST /event-schemas/{id}/validate`, showing
 * that it matches or each problem with its JSON pointer.
 */
export function SampleCheck({ schemaId }: SampleCheckProps) {
  const validate = useValidateEvent()
  const [text, setText] = useState(SAMPLE_START)
  const [touched, setTouched] = useState(false)
  const [state, setState] = useState<CheckState>({ kind: 'idle' })
  const parsed = parseJson(text)
  const parseError = parsed.ok
    ? isJsonObject(parsed.value)
      ? undefined
      : NOT_AN_OBJECT
    : describeParseError(parsed)

  async function check() {
    setTouched(true)
    if (!parsed.ok || !isJsonObject(parsed.value)) return
    const response = await validate.mutateAsync({ schemaId, data: { payload: parsed.value } }).catch(() => null)
    if (response === null) {
      setState({ kind: 'failed', message: OFFLINE })
      return
    }
    switch (response.status) {
      case 200:
        setState({ kind: 'result', result: response.data })
        return
      case 400:
        setState({ kind: 'failed', message: "Couldn't read the sample. Check that it is JSON and try again." })
        return
      case 404:
        setState({ kind: 'failed', message: 'This schema no longer exists. Go back to the list of schemas.' })
        return
      case 422:
        setState({
          kind: 'failed',
          message: bodyIssues(response.data)[0]?.message ?? "Couldn't check the sample. Reload the page and try again.",
        })
        return
      case 401:
        return
      default:
        setState({ kind: 'failed', message: unexpectedStatusMessage(response) })
    }
  }

  return (
    <form
      noValidate
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault()
        void check()
      }}
    >
      <JsonEditor
        label="Sample event"
        description="Paste an event payload as the producer sends it."
        rows={8}
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          setTouched(true)
          setState({ kind: 'idle' })
        }}
        error={touched ? parseError : undefined}
      />
      <div>
        <Button type="submit" variant="secondary" disabled={validate.isPending}>
          {validate.isPending ? 'Checking…' : 'Check sample'}
        </Button>
      </div>
      <div role="status" aria-live="polite">
        <CheckOutcome state={state} />
      </div>
    </form>
  )
}

function CheckOutcome({ state }: { state: CheckState }) {
  switch (state.kind) {
    case 'idle':
      return null
    case 'failed':
      return <p className="text-[12px]/[16px] font-medium text-alert-red-text">{state.message}</p>
    case 'result':
      if (state.result.valid) {
        return (
          <p className="flex items-center gap-2 font-medium">
            <CircleCheck size={16} strokeWidth={1.75} aria-hidden className="text-alert-green" />
            The sample matches the schema.
          </p>
        )
      }
      return (
        <div className="flex flex-col gap-2">
          <p className="flex items-center gap-2 font-medium">
            <CircleX size={16} strokeWidth={1.75} aria-hidden className="text-alert-red" />
            The sample doesn't match the schema.
          </p>
          <ul aria-label="Problems" className="flex flex-col gap-1.5">
            {state.result.issues.map((issue, index) => (
              <li key={index} className="flex flex-wrap gap-x-3">
                <span className="font-mono text-[13px]/[20px] text-alert-red-text">{issue.path === '' ? '/' : issue.path}</span>
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )
    default:
      return state satisfies never
  }
}
