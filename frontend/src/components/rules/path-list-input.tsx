import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { EventField } from '@/lib/event-fields'
import { fieldPathProblem } from '@/lib/rule-condition'
import { FieldPathInput } from './field-path-input'

/** Props for `PathListInput`. */
export interface PathListInputProps {
  /** The paths, in order. */
  value: readonly string[]
  onValueChange: (paths: string[]) => void
  fields: readonly EventField[]
  /** Names the list for screen readers and the add input, e.g. "Fields on the alert". */
  label: string
  /** Most paths allowed; **Add** turns off at the limit. */
  max: number
  disabled?: boolean
  invalid?: boolean
}

/** An ordered list of field paths: a path input with **Add**, and each path as a chip with a remove button. */
export function PathListInput({ value, onValueChange, fields, label, max, disabled, invalid }: PathListInputProps) {
  const [path, setPath] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const full = value.length >= max

  const add = () => {
    const trimmed = path.trim()
    const found = fieldPathProblem(trimmed)
    if (found !== null) {
      setProblem(found)
      return
    }
    setProblem(null)
    setPath('')
    if (!value.includes(trimmed)) onValueChange([...value, trimmed])
  }

  return (
    <div className="flex flex-col gap-2">
      {value.length > 0 && (
        <ul aria-label={label} className="flex flex-wrap gap-1.5">
          {value.map((item) => (
            <li
              key={item}
              className="inline-flex h-6 items-center gap-1 rounded-full bg-muted pr-0.5 pl-2.5 font-mono text-[12px]/[16px]"
            >
              {item}
              {disabled !== true && (
                <button
                  type="button"
                  aria-label={`Remove ${item}`}
                  className="flex size-5 items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
                  onClick={() => onValueChange(value.filter((other) => other !== item))}
                >
                  <X className="size-3" strokeWidth={1.75} aria-hidden />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {disabled !== true && (
        <div className="flex max-w-[480px] items-center gap-2">
          <FieldPathInput
            aria-label={`Add to ${label.toLowerCase()}`}
            value={path}
            onValueChange={setPath}
            fields={fields}
            disabled={full}
            invalid={invalid === true || problem !== null}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.defaultPrevented) {
                event.preventDefault()
                add()
              }
            }}
          />
          <Button type="button" variant="secondary" disabled={full || path.trim() === ''} onClick={add}>
            <Plus strokeWidth={1.75} aria-hidden />
            Add
          </Button>
        </div>
      )}
      {full && disabled !== true && (
        <p className="text-[12px]/[16px] text-muted-foreground">You can add up to {max}.</p>
      )}
      {problem !== null && (
        <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
          {problem}
        </p>
      )}
    </div>
  )
}
