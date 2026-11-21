import { Select as SelectPrimitive } from '@base-ui/react/select'
import { CheckIcon, ChevronDownIcon } from 'lucide-react'
import { layers } from '@/lib/layers'
import { cn } from '@/lib/utils'
import { controlTransition, fieldControl, focusRing, layerMotion, layerSurface, listItem } from './styles'

/** Select root; generic over the option value type. */
export const Select = SelectPrimitive.Root

/** Labelled group of options inside `SelectContent`. */
export const SelectGroup = SelectPrimitive.Group

/** Text of the selected option inside `SelectTrigger`. */
export function SelectValue({ className, ...props }: SelectPrimitive.Value.Props) {
  return (
    <SelectPrimitive.Value
      data-slot="select-value"
      className={cn('flex-1 truncate text-left data-placeholder:text-muted-foreground', className)}
      {...props}
    />
  )
}

/** Button that shows the selected value and opens the list; same box as `Input`. */
export function SelectTrigger({ className, children, ...props }: SelectPrimitive.Trigger.Props) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      className={cn(
        fieldControl,
        controlTransition,
        focusRing,
        'flex w-fit items-center justify-between gap-2 pr-2 whitespace-nowrap select-none',
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon
        render={<ChevronDownIcon className="size-4 text-muted-foreground" strokeWidth={1.75} />}
      />
    </SelectPrimitive.Trigger>
  )
}

/** List of options, portalled on the popover layer below the trigger. */
export function SelectContent({
  className,
  children,
  side = 'bottom',
  sideOffset = 6,
  align = 'start',
  alignOffset = 0,
  alignItemWithTrigger = false,
  ...props
}: SelectPrimitive.Popup.Props &
  Pick<
    SelectPrimitive.Positioner.Props,
    'align' | 'alignOffset' | 'side' | 'sideOffset' | 'alignItemWithTrigger'
  >) {
  return (
    <SelectPrimitive.Portal className="relative isolate" style={{ zIndex: layers.popover }}>
      <SelectPrimitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignOffset={alignOffset}
        alignItemWithTrigger={alignItemWithTrigger}
      >
        <SelectPrimitive.Popup
          data-slot="select-content"
          className={cn(
            'max-h-(--available-height) min-w-(--anchor-width) overflow-y-auto p-1 outline-none',
            layerSurface,
            layerMotion,
            className,
          )}
          {...props}
        >
          <SelectPrimitive.List>{children}</SelectPrimitive.List>
        </SelectPrimitive.Popup>
      </SelectPrimitive.Positioner>
    </SelectPrimitive.Portal>
  )
}

/** Heading of a `SelectGroup`. */
export function SelectLabel({ className, ...props }: SelectPrimitive.GroupLabel.Props) {
  return (
    <SelectPrimitive.GroupLabel
      data-slot="select-label"
      className={cn('px-2 py-1 text-[12px]/[16px] font-medium text-muted-foreground', className)}
      {...props}
    />
  )
}

/** One option; a check marks the selected one. */
export function SelectItem({ className, children, ...props }: SelectPrimitive.Item.Props) {
  return (
    <SelectPrimitive.Item data-slot="select-item" className={cn(listItem, 'pr-8', className)} {...props}>
      <SelectPrimitive.ItemText className="flex flex-1 items-center gap-2 whitespace-nowrap">
        {children}
      </SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator className="absolute right-2 flex items-center">
        <CheckIcon strokeWidth={1.75} />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  )
}
