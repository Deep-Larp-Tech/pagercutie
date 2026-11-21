import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import type { SourceRead } from '@/api/generated/model'
import { getListSourcesQueryKey, useDeleteSource } from '@/api/generated/sources/sources'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { unexpectedStatusMessage } from '@/lib/api'
import { OFFLINE } from '@/lib/pagination'

/** Props for `DeleteSourceDialog`. */
export interface DeleteSourceDialogProps {
  /** The source to delete; `null` closes the dialog. */
  source: SourceRead | null
  onClose: () => void
}

/** Asks before deleting a source, naming it (`DELETE /sources/{id}`). */
export function DeleteSourceDialog({ source, onClose }: DeleteSourceDialogProps) {
  const queryClient = useQueryClient()
  const deleteSource = useDeleteSource()
  const [error, setError] = useState<string | null>(null)

  function close() {
    setError(null)
    onClose()
  }

  async function confirm(target: SourceRead) {
    setError(null)
    const response = await deleteSource.mutateAsync({ sourceId: target.id }).catch(() => null)
    if (response === null) {
      setError(OFFLINE)
      return
    }
    switch (response.status) {
      case 204:
        await queryClient.invalidateQueries({ queryKey: getListSourcesQueryKey() })
        toast.success(`${target.name} deleted`)
        close()
        return
      case 403:
        setError('Only members and leads can delete sources.')
        return
      case 404:
        await queryClient.invalidateQueries({ queryKey: getListSourcesQueryKey() })
        setError('This source no longer exists. Close this dialog to see the current list.')
        return
      case 422:
        setError("Couldn't delete this source. Reload the page and try again.")
        return
      case 401:
        // The sign-in redirect is under way (ADR-0052).
        return
      default:
        setError(unexpectedStatusMessage(response))
    }
  }

  return (
    <ConfirmDialog
      open={source !== null}
      onOpenChange={(open) => !open && close()}
      title={`Delete ${source?.name ?? 'source'}?`}
      description="Events sent to its ingest URL are rejected from then on. This can't be undone."
      confirmLabel="Delete source"
      pendingLabel="Deleting…"
      pending={deleteSource.isPending}
      error={error}
      onConfirm={() => source !== null && void confirm(source)}
    />
  )
}
