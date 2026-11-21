import { Tooltip as TooltipPrimitive } from '@base-ui/react/tooltip'
import { layers } from '@/lib/layers'
import { cn } from '@/lib/utils'
import { layerMotion } from './styles'

/** Shares the open delay between tooltips; mounted once in the root route. */
export function TooltipProvider({ delay = 300, ...props }: TooltipPrimitive.Provider.Props) {
  return <TooltipPrimitive.Provider delay={delay} {...props} />
}

/** Tooltip root; holds the open state. */
export const Tooltip = TooltipPrimitive.Root

/** Element the tooltip describes; pass `render` to use a `Button`. */
export const TooltipTrigger = TooltipPrimitive.Trigger

/** Short plain-language hint, portalled on the popover layer. */
export function TooltipContent({
  className,
  side = 'top',
  sideOffset = 6,
  align = 'center',
  alignOffset = 0,
  ...props
}: TooltipPrimitive.Popup.Props &
  Pick<TooltipPrimitive.Positioner.Props, 'align' | 'alignOffset' | 'side' | 'sideOffset'>) {
  return (
    <TooltipPrimitive.Portal className="fixed top-0 left-0 isolate" style={{ zIndex: layers.popover }}>
      <TooltipPrimitive.Positioner
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
      >
        <TooltipPrimitive.Popup
          data-slot="tooltip-content"
          className={cn(
            'max-w-xs rounded-md border bg-popover px-2 py-1 text-[12px]/[16px] text-popover-foreground shadow-popover',
            layerMotion,
            className,
          )}
          {...props}
        />
      </TooltipPrimitive.Positioner>
    </TooltipPrimitive.Portal>
  )
}
