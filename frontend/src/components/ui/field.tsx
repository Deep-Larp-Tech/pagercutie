import type { ComponentProps } from 'react'
import { Field as FieldPrimitive } from '@base-ui/react/field'
import { Fieldset as FieldsetPrimitive } from '@base-ui/react/fieldset'
import { cn } from '@/lib/utils'

/**
 * One form field: label above, control, helper text below, error below (DESIGN.md §9). Built on Base UI Field,
 * which links the label, description and error to the control; set `invalid` while an error shows.
 */
export function Field({
  className,
  orientation = 'vertical',
  ...props
}: FieldPrimitive.Root.Props & { orientation?: 'vertical' | 'horizontal' }) {
  return (
    <FieldPrimitive.Root
      data-slot="field"
      data-orientation={orientation}
      className={cn(
        'flex w-full gap-1.5 data-[orientation=horizontal]:flex-row data-[orientation=horizontal]:items-center data-[orientation=horizontal]:justify-between data-[orientation=vertical]:flex-col',
        'data-disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}

/** Visible label of the field's control; never replaced by a placeholder. */
export function FieldLabel({ className, ...props }: FieldPrimitive.Label.Props) {
  return (
    <FieldPrimitive.Label
      data-slot="field-label"
      className={cn('w-fit text-[14px]/[20px] font-medium select-none', className)}
      {...props}
    />
  )
}

/** Helper text below the control. */
export function FieldDescription({ className, ...props }: FieldPrimitive.Description.Props) {
  return (
    <FieldPrimitive.Description
      data-slot="field-description"
      className={cn('text-[12px]/[16px] text-muted-foreground', className)}
      {...props}
    />
  )
}

/** Error text below the control, in alert red; render it only while there is an error. */
export function FieldError({ className, ...props }: Omit<FieldPrimitive.Error.Props, 'match'>) {
  return (
    <FieldPrimitive.Error
      data-slot="field-error"
      match
      className={cn('text-[12px]/[16px] font-medium text-alert-red-text', className)}
      {...props}
    />
  )
}

/** Stack of fields with the standard 16 px gap. */
export function FieldGroup({ className, ...props }: ComponentProps<'div'>) {
  return <div data-slot="field-group" className={cn('flex flex-col gap-4', className)} {...props} />
}

/** Group of related fields with a shared legend. */
export function FieldSet({ className, ...props }: FieldsetPrimitive.Root.Props) {
  return (
    <FieldsetPrimitive.Root
      data-slot="field-set"
      className={cn('flex flex-col gap-4', className)}
      {...props}
    />
  )
}

/** Heading of a `FieldSet`. */
export function FieldLegend({ className, ...props }: FieldsetPrimitive.Legend.Props) {
  return (
    <FieldsetPrimitive.Legend
      data-slot="field-legend"
      className={cn('text-[15px]/[22px] font-semibold', className)}
      {...props}
    />
  )
}
