import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/** Standalone form label; inside a `Field` use `FieldLabel`, which links itself to the control. */
export function Label({ className, ...props }: ComponentProps<'label'>) {
  return (
    <label
      data-slot="label"
      className={cn('text-[14px]/[20px] font-medium select-none', className)}
      {...props}
    />
  )
}
