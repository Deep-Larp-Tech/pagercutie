import { Combobox as ComboboxPrimitive } from '@base-ui/react/combobox'
import { CheckIcon, ChevronDownIcon } from 'lucide-react'
import { layers } from '@/lib/layers'
import { cn } from '@/lib/utils'
import { controlTransition, fieldControl, focusRing, layerMotion, layerSurface, listItem } from './styles'

/** Combobox root: a text input that filters a list; generic over the item value type. Keyboard first (DESIGN.md §9). */
export const Combobox = ComboboxPrimitive.Root

/** The text input with a button that opens the list; same box as `Input`. Label it with a `FieldLabel`. */
export function ComboboxInput({ className, ...props }: ComboboxPrimitive.Input.Props) {
  return (
    <ComboboxPrimitive.InputGroup className={cn('relative w-full', className)}>
      <ComboboxPrimitive.Input
        data-slot="combobox-input"
        className={cn(fieldControl, controlTransition, focusRing, 'py-1 pr-8')}
        {...props}
      />
      <ComboboxPrimitive.Trigger
        aria-label="Show options"
        className={cn(
          'absolute top-0 right-0 flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground',
          focusRing,
        )}
      >
        <ChevronDownIcon className="size-4" strokeWidth={1.75} aria-hidden />
      </ComboboxPrimitive.Trigger>
    </ComboboxPrimitive.InputGroup>
  )
}

/** The option list, portalled on the popover layer below the input; `empty` shows when no option matches. */
export function ComboboxContent({
  className,
  children,
  empty,
  ...props
}: ComboboxPrimitive.List.Props & { empty: string }) {
  return (
    <ComboboxPrimitive.Portal className="fixed top-0 left-0 isolate" style={{ zIndex: layers.popover }}>
      <ComboboxPrimitive.Positioner sideOffset={6} align="start">
        <ComboboxPrimitive.Popup
          data-slot="combobox-content"
          className={cn('w-(--anchor-width) max-w-(--available-width) p-1', layerSurface, layerMotion)}
        >
          <ComboboxPrimitive.Empty className="px-2 py-1.5 text-[12px]/[16px] text-muted-foreground empty:hidden">
            {empty}
          </ComboboxPrimitive.Empty>
          <ComboboxPrimitive.List
            className={cn('max-h-[min(20rem,var(--available-height))] overflow-y-auto outline-none', className)}
            {...props}
          >
            {children}
          </ComboboxPrimitive.List>
        </ComboboxPrimitive.Popup>
      </ComboboxPrimitive.Positioner>
    </ComboboxPrimitive.Portal>
  )
}

/** One option; a check marks the selected one. */
export function ComboboxItem({ className, children, ...props }: ComboboxPrimitive.Item.Props) {
  return (
    <ComboboxPrimitive.Item data-slot="combobox-item" className={cn(listItem, 'pr-8', className)} {...props}>
      <span className="flex min-w-0 flex-1 items-center gap-2">{children}</span>
      <ComboboxPrimitive.ItemIndicator className="absolute right-2 flex items-center">
        <CheckIcon strokeWidth={1.75} />
      </ComboboxPrimitive.ItemIndicator>
    </ComboboxPrimitive.Item>
  )
}
