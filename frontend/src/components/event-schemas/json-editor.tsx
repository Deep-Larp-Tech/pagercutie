import type { ComponentProps } from 'react'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

/** Props for `JsonEditor`; the rest go to the textarea (`register(…)` output, `value`, `onChange`). */
export interface JsonEditorProps extends Omit<ComponentProps<'textarea'>, 'children'> {
  /** Visible label above the editor. */
  label: string
  /** Helper text under the editor. */
  description?: string
  /** What is wrong with the text: a JSON parse error with line and column, or a server error; `undefined` when fine. */
  error?: string
}

/** JSON text area in Geist Mono with the parse or validation error inline under it. */
export function JsonEditor({ label, description, error, className, rows = 14, ...props }: JsonEditorProps) {
  return (
    <Field invalid={error !== undefined}>
      <FieldLabel>{label}</FieldLabel>
      <Textarea
        rows={rows}
        spellCheck={false}
        autoComplete="off"
        autoCapitalize="off"
        className={cn('font-mono text-[13px]/[20px] [tab-size:2]', className)}
        {...props}
      />
      {description !== undefined && <FieldDescription>{description}</FieldDescription>}
      {error !== undefined && <FieldError>{error}</FieldError>}
    </Field>
  )
}
