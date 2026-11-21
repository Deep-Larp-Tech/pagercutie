import { useId } from 'react'
import { Toggle as TogglePrimitive } from '@base-ui/react/toggle'
import { ToggleGroup as ToggleGroupPrimitive } from '@base-ui/react/toggle-group'
import type { LucideIcon } from 'lucide-react'
import { LayoutGroup, motion } from 'motion/react'
import { motionTokens } from '@/lib/motion'
import { cn } from '@/lib/utils'
import { controlTransition, focusRing } from './styles'

/** One option of a `SegmentedControl`. */
export interface SegmentedOption<Value extends string> {
  value: Value
  /** Visible label in sentence case. */
  label: string
  /** Optional icon before the label, drawn at 14 px. */
  icon?: LucideIcon
}

/** Props for `SegmentedControl`. */
export interface SegmentedControlProps<Value extends string> {
  options: readonly SegmentedOption<Value>[]
  /** The selected option; exactly one is always selected. */
  value: Value
  onValueChange: (value: Value) => void
  /** Accessible name of the group, e.g. "Channel". */
  'aria-label': string
  className?: string
}

/**
 * Row of mutually exclusive options for filtering a view. The selected one is violet on an `--accent` highlight that
 * slides between options (DESIGN.md §8), like the sidebar's active item.
 */
export function SegmentedControl<Value extends string>({
  options,
  value,
  onValueChange,
  'aria-label': ariaLabel,
  className,
}: SegmentedControlProps<Value>) {
  // Two controls on one page each keep their own highlight.
  const group = useId()
  return (
    <LayoutGroup id={group}>
      <ToggleGroupPrimitive<Value>
        aria-label={ariaLabel}
        value={[value]}
        onValueChange={([next]) => {
          // Pressing the selected option again would leave nothing selected; keep it.
          if (next !== undefined) onValueChange(next)
        }}
        className={cn('flex w-fit items-center gap-0.5 rounded-md border p-0.5', className)}
      >
        {options.map(({ value: option, label, icon: Icon }) => (
          <TogglePrimitive<Value>
            key={option}
            value={option}
            className={cn(
              'relative isolate inline-flex h-6 items-center gap-1.5 rounded-[6px] px-2.5 text-[12px]/[16px] font-medium whitespace-nowrap text-muted-foreground',
              'hover:text-foreground data-pressed:text-primary active:scale-97',
              controlTransition,
              focusRing,
            )}
          >
            {option === value && (
              <motion.span
                layoutId="segmented-highlight"
                className="absolute inset-0 -z-10 rounded-[6px] bg-accent"
                transition={motionTokens.spring}
              />
            )}
            {Icon !== undefined && <Icon size={14} strokeWidth={1.75} aria-hidden />}
            {label}
          </TogglePrimitive>
        ))}
      </ToggleGroupPrimitive>
    </LayoutGroup>
  )
}
