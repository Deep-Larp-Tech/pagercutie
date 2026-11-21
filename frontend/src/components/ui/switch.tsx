import { Switch as SwitchPrimitive } from '@base-ui/react/switch'
import { cn } from '@/lib/utils'
import { controlTransition, focusRing } from './styles'

/** On/off switch, 32 × 18 px with a full radius (DESIGN.md §7). */
export function Switch({ className, ...props }: SwitchPrimitive.Root.Props) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        'group/switch relative inline-flex h-[18px] w-8 shrink-0 items-center rounded-full border border-transparent p-px',
        'data-checked:bg-primary data-unchecked:bg-input',
        'data-disabled:cursor-not-allowed data-disabled:opacity-50',
        controlTransition,
        focusRing,
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className={cn(
          'pointer-events-none block size-3.5 rounded-full bg-background shadow-card',
          'data-checked:translate-x-3.5 data-unchecked:translate-x-0',
          controlTransition,
        )}
      />
    </SwitchPrimitive.Root>
  )
}
