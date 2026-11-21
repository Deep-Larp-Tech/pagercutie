import type { ComponentProps } from 'react'
import { Dialog as DialogPrimitive } from '@base-ui/react/dialog'
import { XIcon } from 'lucide-react'
import { layers } from '@/lib/layers'
import { cn } from '@/lib/utils'
import { Button } from './button'
import { layerMotion, layerSurface } from './styles'

/** Dialog root; traps focus while open and returns it to the trigger on close. */
export const Dialog = DialogPrimitive.Root

/** Element that opens the dialog; pass `render` to use a `Button`. */
export const DialogTrigger = DialogPrimitive.Trigger

/** Closes the dialog; pass `render` to use a `Button`. */
export const DialogClose = DialogPrimitive.Close

/** Modal panel with backdrop, portalled on the dialog layer (DESIGN.md §7). */
export function DialogContent({
  className,
  children,
  showCloseButton = true,
  ...props
}: DialogPrimitive.Popup.Props & { showCloseButton?: boolean }) {
  return (
    // Layers opened inside the dialog portal into this node, so its stacking context keeps them above the popup.
    <DialogPrimitive.Portal className="relative isolate" style={{ zIndex: layers.dialog }}>
      <DialogPrimitive.Backdrop
        data-slot="dialog-overlay"
        className={cn(
          'fixed inset-0 bg-foreground/20',
          'data-open:animate-in data-open:fade-in-0 data-open:duration-(--duration-base) data-closed:animate-out data-closed:fade-out-0 data-closed:duration-(--duration-exit)',
        )}
      />
      <DialogPrimitive.Popup
        data-slot="dialog-content"
        className={cn(
          'fixed top-1/2 left-1/2 flex w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 p-5 text-sm outline-none sm:max-w-md',
          layerSurface,
          layerMotion,
          className,
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <DialogPrimitive.Close
            data-slot="dialog-close"
            aria-label="Close"
            render={<Button variant="ghost" size="icon-sm" className="absolute top-3 right-3" />}
          >
            <XIcon strokeWidth={1.75} />
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Popup>
    </DialogPrimitive.Portal>
  )
}

/** Title and description block at the top of a dialog. */
export function DialogHeader({ className, ...props }: ComponentProps<'div'>) {
  return <div data-slot="dialog-header" className={cn('flex flex-col gap-1 pr-8', className)} {...props} />
}

/** Action row at the bottom of a dialog; the primary action goes last. */
export function DialogFooter({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end', className)}
      {...props}
    />
  )
}

/** Dialog heading, announced as the dialog's accessible name. */
export function DialogTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn('text-[18px]/[26px] font-semibold tracking-[-0.01em]', className)}
      {...props}
    />
  )
}

/** Supporting text under the dialog title. */
export function DialogDescription({ className, ...props }: DialogPrimitive.Description.Props) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn('text-muted-foreground', className)}
      {...props}
    />
  )
}
