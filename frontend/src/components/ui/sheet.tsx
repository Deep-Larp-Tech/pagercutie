import { Dialog as SheetPrimitive } from '@base-ui/react/dialog'
import { XIcon } from 'lucide-react'
import { layers } from '@/lib/layers'
import { cn } from '@/lib/utils'
import { Button } from './button'

/** Sheet root; a modal dialog that traps focus while open and returns it to the trigger on close. */
export const Sheet = SheetPrimitive.Root

/** Element that opens the sheet; pass `render` to use a `Button`. */
export const SheetTrigger = SheetPrimitive.Trigger

/** Closes the sheet; pass `render` to use a `Link` or `Button`. */
export const SheetClose = SheetPrimitive.Close

/** Panel that slides in from the left edge over a backdrop, portalled on the dialog layer (DESIGN.md §7). */
export function SheetContent({
  className,
  children,
  showCloseButton = true,
  ...props
}: SheetPrimitive.Popup.Props & { showCloseButton?: boolean }) {
  return (
    <SheetPrimitive.Portal className="fixed top-0 left-0 isolate" style={{ zIndex: layers.dialog }}>
      <SheetPrimitive.Backdrop
        data-slot="sheet-overlay"
        className={cn(
          'fixed inset-0 bg-foreground/20 transition-opacity duration-(--duration-base) ease-standard',
          'data-ending-style:opacity-0 data-ending-style:duration-(--duration-exit) data-starting-style:opacity-0',
        )}
      />
      <SheetPrimitive.Popup
        data-slot="sheet-content"
        className={cn(
          'fixed inset-y-0 left-0 flex h-full w-[280px] max-w-[calc(100%-3rem)] flex-col border-r bg-background text-sm shadow-popover outline-none',
          'transition-[translate,opacity] duration-(--duration-base) ease-standard',
          'data-ending-style:-translate-x-10 data-ending-style:opacity-0 data-ending-style:duration-(--duration-exit) data-ending-style:ease-exit',
          'data-starting-style:-translate-x-10 data-starting-style:opacity-0',
          className,
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <SheetPrimitive.Close
            data-slot="sheet-close"
            aria-label="Close"
            render={<Button variant="ghost" size="icon-sm" className="absolute top-3 right-3" />}
          >
            <XIcon strokeWidth={1.75} />
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Popup>
    </SheetPrimitive.Portal>
  )
}

/** Sheet heading, announced as its accessible name; pass `className="sr-only"` to keep it for screen readers only. */
export function SheetTitle({ className, ...props }: SheetPrimitive.Title.Props) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn('text-[18px]/[26px] font-semibold tracking-[-0.01em]', className)}
      {...props}
    />
  )
}
