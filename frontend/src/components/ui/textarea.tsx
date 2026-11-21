import type { ComponentProps } from 'react'
import { Field as FieldPrimitive } from '@base-ui/react/field'
import { cn } from '@/lib/utils'
import { controlTransition, focusRing } from './styles'

/** Multi-line text input; inside a `Field` it picks up the label, description and invalid state like `Input`. */
export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return (
    <FieldPrimitive.Control
      render={
        <textarea
          data-slot="textarea"
          className={cn(
            'min-h-20 w-full min-w-0 rounded-md border border-input bg-transparent px-2.5 py-1.5 text-sm placeholder:text-muted-foreground',
            'disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-alert-red aria-invalid:focus-visible:ring-alert-red',
            controlTransition,
            focusRing,
            className,
          )}
          {...props}
        />
      }
    />
  )
}
