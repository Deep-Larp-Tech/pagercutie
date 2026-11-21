import { useState } from 'react'
import { UsersRound } from 'lucide-react'
import type { UserRead } from '@/api/generated/model'
import { getListUsersQueryKey, listUsers, type listUsersResponse } from '@/api/generated/users/users'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { unexpectedStatusMessage } from '@/lib/api'
import { useOffsetPages, type PageResult } from '@/lib/pagination'
import { useMe } from '@/lib/session'
import { AddUserDialog } from './add-user-dialog'
import { DeleteUserDialog } from './delete-user-dialog'
import { EditUserDialog } from './edit-user-dialog'
import { ListFailed, RowActions, ShowMore, SkeletonRows } from './list-parts'
import { globalRoleLabel } from './copy'

const COLUMNS = 4

/** Reads one `GET /users` page. */
function readUsersPage(response: listUsersResponse): PageResult<UserRead> {
  switch (response.status) {
    case 200:
      return { kind: 'items', items: response.data }
    case 401:
      return { kind: 'silent' }
    case 422:
      return { kind: 'failed', message: 'The list request was not valid. Reload the page and try again.' }
    default:
      return { kind: 'failed', message: unexpectedStatusMessage(response) }
  }
}

/** `/admin/users`: every user with their global role; admins add, edit and delete users here. */
export function UsersPage() {
  const me = useMe()
  const pages = useOffsetPages(
    [...getListUsersQueryKey(), 'pages'],
    (params, signal) => listUsers(params, { signal }),
    readUsersPage,
  )
  const [editing, setEditing] = useState<UserRead | null>(null)
  const [deleting, setDeleting] = useState<UserRead | null>(null)
  const { list } = pages

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Users" description="Everyone who can sign in, and their global role." actions={<AddUserDialog />} />
      {list.kind === 'failed' ? (
        <ListFailed title="Couldn't load users" message={list.message} onRetry={pages.retry} />
      ) : list.kind === 'listed' && list.items.length === 0 ? (
        <EmptyState icon={UsersRound} title="No users yet" description="Add the first user with Add user." />
      ) : (
        <Table aria-label="Users" aria-busy={list.kind === 'loading'}>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Global role</TableHead>
              <TableHead>
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.kind === 'loading' ? (
              <SkeletonRows columns={COLUMNS} />
            ) : (
              list.items.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium">
                    {user.display_name}
                    {user.id === me.user.id && <span className="ml-2 text-muted-foreground">(you)</span>}
                  </TableCell>
                  <TableCell className="font-mono text-[13px]/[20px] text-muted-foreground">{user.email}</TableCell>
                  <TableCell>
                    <Badge>{globalRoleLabel[user.role]}</Badge>
                  </TableCell>
                  <TableCell className="w-10 text-right">
                    <RowActions
                      name={user.display_name}
                      editLabel="Edit user"
                      deleteLabel="Delete user"
                      onEdit={() => setEditing(user)}
                      onDelete={user.id === me.user.id ? undefined : () => setDeleting(user)}
                    />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
      <ShowMore pages={pages} />
      <EditUserDialog user={editing} onClose={() => setEditing(null)} />
      <DeleteUserDialog user={deleting} onClose={() => setDeleting(null)} />
    </div>
  )
}
