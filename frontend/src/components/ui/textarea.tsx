import type { ComponentProps } from 'react'
import { Field as FieldPrimitive } from '@base-ui/react/field'
import { cn } from '@/lib/utils'
import { controlTransition, fieldControl, focusRing } from './styles'

/**
 * Multi-line text input with the `Input` look; grows with its rows instead of the fixed 32 px height. Rendered as the
 * Base UI field control, so a surrounding `Field` labels and describes it.
 */
export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return (
    <FieldPrimitive.Control
      render={
        <textarea
          data-slot="textarea"
          className={cn(fieldControl, controlTransition, focusRing, 'h-auto min-h-16 py-1.5', className)}
          {...props}
        />
      }
    />
  )
}
