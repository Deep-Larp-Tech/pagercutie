import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import type { RunbookRead } from '@/api/generated/model'
import { getGetRunbookQueryKey, getListRunbooksQueryKey, useDeleteRunbook } from '@/api/generated/runbooks/runbooks'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { unexpectedStatusMessage } from '@/lib/api'
import { OFFLINE } from '@/lib/pagination'
import { RUNBOOK_GONE } from './messages'

/** Props for `DeleteRunbookDialog`. */
export interface DeleteRunbookDialogProps {
  runbook: RunbookRead
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called after the runbook is deleted, to leave its page. */
  onDeleted: () => void
}

/** Asks before deleting a runbook, naming it (`DELETE /runbooks/{id}`); failures show inline. */
export function DeleteRunbookDialog({ runbook, open, onOpenChange, onDeleted }: DeleteRunbookDialogProps) {
  const queryClient = useQueryClient()
  const deleteRunbook = useDeleteRunbook()
  const [error, setError] = useState<string | null>(null)

  function close() {
    setError(null)
    onOpenChange(false)
  }

  async function confirm() {
    setError(null)
    const response = await deleteRunbook.mutateAsync({ runbookId: runbook.id }).catch(() => null)
    if (response === null) {
      setError(OFFLINE)
      return
    }
    switch (response.status) {
      case 204:
        queryClient.removeQueries({ queryKey: getGetRunbookQueryKey(runbook.id) })
        await queryClient.invalidateQueries({ queryKey: getListRunbooksQueryKey() })
        toast.success(`${runbook.title} deleted`)
        close()
        onDeleted()
        return
      case 403:
        setError("You can't delete this team's runbooks. Ask a team lead to make you a member.")
        return
      case 404:
        await queryClient.invalidateQueries({ queryKey: getListRunbooksQueryKey() })
        setError(RUNBOOK_GONE)
        return
      case 422:
        setError("Couldn't delete this runbook. Reload the page and try again.")
        return
      case 401:
        return
      default:
        setError(unexpectedStatusMessage(response))
    }
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title={`Delete ${runbook.title}?`}
      description="Its text and steps are removed. This can't be undone."
      confirmLabel="Delete runbook"
      pendingLabel="Deleting…"
      pending={deleteRunbook.isPending}
      error={error}
      onConfirm={() => void confirm()}
    />
  )
}
