import type { ComponentProps } from 'react'
import { Input as InputPrimitive } from '@base-ui/react/input'
import { cn } from '@/lib/utils'
import { controlTransition, fieldControl, focusRing } from './styles'

/** Single-line text input; inside a `Field` it picks up the label, description and invalid state. */
export function Input({ className, ...props }: ComponentProps<typeof InputPrimitive>) {
  return (
    <InputPrimitive
      data-slot="input"
      className={cn(fieldControl, controlTransition, focusRing, 'py-1', className)}
      {...props}
    />
  )
}
