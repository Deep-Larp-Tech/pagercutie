import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import type { UserRead } from '@/api/generated/model'
import { getListUsersQueryKey, useDeleteUser } from '@/api/generated/users/users'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { unexpectedStatusMessage } from '@/lib/api'
import { OFFLINE } from '@/lib/pagination'

/** Props for `DeleteUserDialog`. */
export interface DeleteUserDialogProps {
  /** The user to delete; `null` closes the dialog. */
  user: UserRead | null
  onClose: () => void
}

/** Asks before deleting a user, naming them (`DELETE /users/{id}`). */
export function DeleteUserDialog({ user, onClose }: DeleteUserDialogProps) {
  const queryClient = useQueryClient()
  const deleteUser = useDeleteUser()
  const [error, setError] = useState<string | null>(null)

  function close() {
    setError(null)
    onClose()
  }

  async function confirm(target: UserRead) {
    setError(null)
    const response = await deleteUser.mutateAsync({ userId: target.id }).catch(() => null)
    if (response === null) {
      setError(OFFLINE)
      return
    }
    switch (response.status) {
      case 204:
        await queryClient.invalidateQueries({ queryKey: getListUsersQueryKey() })
        toast.success(`${target.display_name} deleted`)
        close()
        return
      case 403:
        setError('Only admins can delete users.')
        return
      case 404:
        await queryClient.invalidateQueries({ queryKey: getListUsersQueryKey() })
        setError('This user no longer exists. Close this dialog to see the current list.')
        return
      case 422:
        setError("Couldn't delete this user. Reload the page and try again.")
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
      open={user !== null}
      onOpenChange={(open) => !open && close()}
      title={`Delete ${user?.display_name ?? 'user'}?`}
      description="They can no longer sign in, and they leave every team and rotation. This can't be undone."
      confirmLabel="Delete user"
      pendingLabel="Deleting…"
      pending={deleteUser.isPending}
      error={error}
      onConfirm={() => user !== null && void confirm(user)}
    />
  )
}
