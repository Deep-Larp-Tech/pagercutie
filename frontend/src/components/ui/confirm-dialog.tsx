import { Button } from './button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './dialog'

/** Props for `ConfirmDialog`. */
export interface ConfirmDialogProps {
  /** Whether the dialog shows. */
  open: boolean
  /** Called with `false` when the user cancels or presses Escape. */
  onOpenChange: (open: boolean) => void
  /** Question that names the thing affected, e.g. "Delete Anna Novak?". */
  title: string
  /** What happens after confirming, in one or two sentences. */
  description: string
  /** Label of the destructive button, e.g. "Delete user". */
  confirmLabel: string
  /** Label while the action runs, e.g. "Deleting…". */
  pendingLabel: string
  /** Whether the action is running; disables both buttons. */
  pending: boolean
  /** Why the last attempt failed, shown above the buttons; `null` when there is nothing to show. */
  error: string | null
  /** Runs the action; the caller closes the dialog when it succeeds. */
  onConfirm: () => void
}

/** Asks before an irreversible action; the destructive button goes last, and a failure shows inline. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  pendingLabel,
  pending,
  error,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent role="alertdialog" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {error !== null && (
          <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
            {error}
          </p>
        )}
        <DialogFooter>
          <DialogClose render={<Button variant="secondary" disabled={pending} />}>Cancel</DialogClose>
          <Button variant="destructive" disabled={pending} onClick={onConfirm}>
            {pending ? pendingLabel : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
