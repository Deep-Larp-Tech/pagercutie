import { createContext, useContext } from 'react'
import { Toggle as TogglePrimitive } from '@base-ui/react/toggle'
import { ToggleGroup as ToggleGroupPrimitive } from '@base-ui/react/toggle-group'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'
import { controlTransition, focusRing } from './styles'

/** Class names for each toggle size; pressed toggles take the primary colour. */
const toggleVariants = cva(
  [
    'inline-flex items-center justify-center gap-1.5 rounded-[6px] font-medium whitespace-nowrap text-muted-foreground',
    'hover:bg-accent hover:text-foreground data-pressed:bg-primary data-pressed:text-primary-foreground',
    'active:scale-97 disabled:pointer-events-none disabled:opacity-50',
    '[&_svg]:pointer-events-none [&_svg]:shrink-0',
    controlTransition,
    focusRing,
  ],
  {
    variants: {
      size: {
        sm: 'h-6 min-w-6 px-2.5 text-[12px]/[16px] [&_svg]:size-3.5',
        md: 'h-7 min-w-7 px-3 text-[14px]/[20px] [&_svg]:size-4',
      },
    },
    defaultVariants: {
      size: 'sm',
    },
  },
)

type ToggleSize = VariantProps<typeof toggleVariants>['size']

const ToggleGroupSize = createContext<ToggleSize>('sm')

/** Segmented control: a bordered row of toggles, one pressed at a time unless `multiple` is set. */
export function ToggleGroup<Value extends string>({
  className,
  size = 'sm',
  children,
  ...props
}: ToggleGroupPrimitive.Props<Value> & { size?: ToggleSize }) {
  return (
    <ToggleGroupPrimitive
      data-slot="toggle-group"
      className={cn(
        'flex w-fit items-center gap-0.5 rounded-md border p-0.5 data-[orientation=vertical]:flex-col',
        className,
      )}
      {...props}
    >
      <ToggleGroupSize value={size}>{children}</ToggleGroupSize>
    </ToggleGroupPrimitive>
  )
}

/** One option of a `ToggleGroup`; `value` identifies it in the group's value array. */
export function ToggleGroupItem<Value extends string>({
  className,
  ...props
}: TogglePrimitive.Props<Value>) {
  const size = useContext(ToggleGroupSize)
  return (
    <TogglePrimitive
      data-slot="toggle-group-item"
      className={cn(toggleVariants({ size }), className)}
      {...props}
    />
  )
}
