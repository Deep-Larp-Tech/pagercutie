import { Menu as MenuPrimitive } from '@base-ui/react/menu'
import { layers } from '@/lib/layers'
import { cn } from '@/lib/utils'
import { layerMotion, layerSurface, listItem } from './styles'

/** Menu root; holds the open state. */
export const DropdownMenu = MenuPrimitive.Root

/** Element that opens the menu; pass `render` to use a `Button`. */
export const DropdownMenuTrigger = MenuPrimitive.Trigger

/** Group of related items, optionally headed by a `DropdownMenuLabel`. */
export const DropdownMenuGroup = MenuPrimitive.Group

/** Menu panel, portalled on the popover layer (DESIGN.md §7). */
export function DropdownMenuContent({
  align = 'start',
  alignOffset = 0,
  side = 'bottom',
  sideOffset = 6,
  className,
  ...props
}: MenuPrimitive.Popup.Props &
  Pick<MenuPrimitive.Positioner.Props, 'align' | 'alignOffset' | 'side' | 'sideOffset'>) {
  return (
    <MenuPrimitive.Portal className="relative isolate" style={{ zIndex: layers.popover }}>
      <MenuPrimitive.Positioner
        className="outline-none"
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
      >
        <MenuPrimitive.Popup
          data-slot="dropdown-menu-content"
          className={cn(
            'max-h-(--available-height) min-w-40 overflow-y-auto p-1 outline-none',
            layerSurface,
            layerMotion,
            className,
          )}
          {...props}
        />
      </MenuPrimitive.Positioner>
    </MenuPrimitive.Portal>
  )
}

/** Heading of a `DropdownMenuGroup`. */
export function DropdownMenuLabel({ className, ...props }: MenuPrimitive.GroupLabel.Props) {
  return (
    <MenuPrimitive.GroupLabel
      data-slot="dropdown-menu-label"
      className={cn('px-2 py-1 text-[12px]/[16px] font-medium text-muted-foreground', className)}
      {...props}
    />
  )
}

/** One action; `destructive` colours it alert red for irreversible actions. */
export function DropdownMenuItem({
  className,
  variant = 'default',
  ...props
}: MenuPrimitive.Item.Props & { variant?: 'default' | 'destructive' }) {
  return (
    <MenuPrimitive.Item
      data-slot="dropdown-menu-item"
      data-variant={variant}
      className={cn(
        listItem,
        'data-[variant=destructive]:text-alert-red-text data-[variant=destructive]:data-highlighted:bg-alert-red-tint data-[variant=destructive]:data-highlighted:text-alert-red-text data-[variant=destructive]:[&_svg]:text-alert-red-text',
        className,
      )}
      {...props}
    />
  )
}

/** Divider between groups of items. */
export function DropdownMenuSeparator({ className, ...props }: MenuPrimitive.Separator.Props) {
  return (
    <MenuPrimitive.Separator
      data-slot="dropdown-menu-separator"
      className={cn('-mx-1 my-1 h-px bg-border', className)}
      {...props}
    />
  )
}
