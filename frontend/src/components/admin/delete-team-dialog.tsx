import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import { toast } from 'sonner'
import type { TeamRead } from '@/api/generated/model'
import { getListTeamsQueryKey, useDeleteTeam } from '@/api/generated/teams/teams'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { unexpectedStatusMessage } from '@/lib/api'
import { OFFLINE } from '@/lib/pagination'
import { meQueryOptions } from '@/lib/session'

/** Props for `DeleteTeamDialog`. */
export interface DeleteTeamDialogProps {
  /** The team to delete; `null` closes the dialog. */
  team: TeamRead | null
  onClose: () => void
}

/** Asks before deleting a team, naming it (`DELETE /teams/{id}`); a `409` shows the server's reason inline. */
export function DeleteTeamDialog({ team, onClose }: DeleteTeamDialogProps) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const deleteTeam = useDeleteTeam()
  const [error, setError] = useState<string | null>(null)

  function close() {
    setError(null)
    onClose()
  }

  async function confirm(target: TeamRead) {
    setError(null)
    const response = await deleteTeam.mutateAsync({ teamId: target.id }).catch(() => null)
    if (response === null) {
      setError(OFFLINE)
      return
    }
    switch (response.status) {
      case 204:
        await queryClient.invalidateQueries({ queryKey: getListTeamsQueryKey() })
        await queryClient.invalidateQueries(meQueryOptions)
        await router.invalidate()
        toast.success(`${target.name} deleted`)
        close()
        return
      case 409:
        // The team still owns something (sources, rules, runbooks); the server names it.
        setError(response.data.detail)
        return
      case 403:
        setError('Only admins can delete teams.')
        return
      case 404:
        await queryClient.invalidateQueries({ queryKey: getListTeamsQueryKey() })
        setError('This team no longer exists. Close this dialog to see the current list.')
        return
      case 422:
        setError("Couldn't delete this team. Reload the page and try again.")
        return
      case 401:
        // The sign-in redirect is under way (ADR-0048).
        return
      default:
        setError(unexpectedStatusMessage(response))
    }
  }

  return (
    <ConfirmDialog
      open={team !== null}
      onOpenChange={(open) => !open && close()}
      title={`Delete ${team?.name ?? 'team'}?`}
      description="Its members, rotation and notification settings go with it. This can't be undone."
      confirmLabel="Delete team"
      pendingLabel="Deleting…"
      pending={deleteTeam.isPending}
      error={error}
      onConfirm={() => team !== null && void confirm(team)}
    />
  )
}
