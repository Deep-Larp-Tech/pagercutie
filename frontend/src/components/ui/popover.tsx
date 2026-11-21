import { Popover as PopoverPrimitive } from '@base-ui/react/popover'
import { layers } from '@/lib/layers'
import { cn } from '@/lib/utils'
import { layerMotion, layerSurface } from './styles'

/** Popover root; holds the open state. */
export const Popover = PopoverPrimitive.Root

/** Element that opens the popover; pass `render` to use a `Button`. */
export const PopoverTrigger = PopoverPrimitive.Trigger

/** Floating panel, portalled on the popover layer (DESIGN.md §7). */
export function PopoverContent({
  className,
  align = 'center',
  alignOffset = 0,
  side = 'bottom',
  sideOffset = 6,
  ...props
}: PopoverPrimitive.Popup.Props &
  Pick<PopoverPrimitive.Positioner.Props, 'align' | 'alignOffset' | 'side' | 'sideOffset'>) {
  return (
    <PopoverPrimitive.Portal className="relative isolate" style={{ zIndex: layers.popover }}>
      <PopoverPrimitive.Positioner
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
      >
        <PopoverPrimitive.Popup
          data-slot="popover-content"
          className={cn(
            'flex w-72 flex-col gap-2 p-3 text-sm outline-none',
            layerSurface,
            layerMotion,
            className,
          )}
          {...props}
        />
      </PopoverPrimitive.Positioner>
    </PopoverPrimitive.Portal>
  )
}

/** Popover heading, announced as the popover's accessible name. */
export function PopoverTitle({ className, ...props }: PopoverPrimitive.Title.Props) {
  return (
    <PopoverPrimitive.Title
      data-slot="popover-title"
      className={cn('text-[14px]/[20px] font-semibold', className)}
      {...props}
    />
  )
}

/** Supporting text under the popover title. */
export function PopoverDescription({ className, ...props }: PopoverPrimitive.Description.Props) {
  return (
    <PopoverPrimitive.Description
      data-slot="popover-description"
      className={cn('text-muted-foreground', className)}
      {...props}
    />
  )
}
