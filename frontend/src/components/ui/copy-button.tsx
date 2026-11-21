import { useEffect, useState } from 'react'
import { Check, Copy, X } from 'lucide-react'
import { Button } from './button'

/** How long the button shows its result before it turns back into a copy icon (ms). */
const RESULT_MS = 2000

type CopyState = 'idle' | 'copied' | 'failed'

const stateMessage = {
  idle: '',
  copied: 'Copied',
  failed: "Couldn't copy. Select the text and copy it.",
} as const satisfies Record<CopyState, string>

/** Props for `CopyButton`. */
export interface CopyButtonProps {
  /** Text put on the clipboard. */
  value: string
  /** Accessible name saying what is copied, e.g. "Copy ingest URL". */
  label: string
}

/** Icon button that copies `value`; a check (or a cross on failure) and a status message confirm it. */
export function CopyButton({ value, label }: CopyButtonProps) {
  const [state, setState] = useState<CopyState>('idle')

  useEffect(() => {
    if (state === 'idle') return
    const timer = window.setTimeout(() => setState('idle'), RESULT_MS)
    return () => window.clearTimeout(timer)
  }, [state])

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setState('copied')
    } catch {
      setState('failed')
    }
  }

  const Icon = state === 'copied' ? Check : state === 'failed' ? X : Copy
  return (
    <>
      <Button type="button" variant="ghost" size="icon-sm" aria-label={label} onClick={() => void copy()}>
        <Icon strokeWidth={1.75} aria-hidden />
      </Button>
      <span role="status" className="sr-only">
        {stateMessage[state]}
      </span>
    </>
  )
}
