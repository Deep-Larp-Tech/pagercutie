import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { UsersRound } from 'lucide-react'
import type { TeamRead } from '@/api/generated/model'
import { getListTeamsQueryKey, listTeams, type listTeamsResponse } from '@/api/generated/teams/teams'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { unexpectedStatusMessage } from '@/lib/api'
import { useOffsetPages, type PageResult } from '@/lib/pagination'
import { AddTeamDialog } from './add-team-dialog'
import { DeleteTeamDialog } from './delete-team-dialog'
import { EditTeamDialog } from './edit-team-dialog'
import { ListFailed, RowActions, ShowMore, SkeletonRows } from './list-parts'

const COLUMNS = 4

/** Reads one `GET /teams` page. */
function readTeamsPage(response: listTeamsResponse): PageResult<TeamRead> {
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

/** `/admin/teams`: every team; admins add, edit and delete teams here. */
export function TeamsPage() {
  const pages = useOffsetPages(
    [...getListTeamsQueryKey(), 'pages'],
    (params, signal) => listTeams(params, { signal }),
    readTeamsPage,
  )
  const [editing, setEditing] = useState<TeamRead | null>(null)
  const [deleting, setDeleting] = useState<TeamRead | null>(null)
  const { list } = pages

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Teams" description="Every team. Open one to see its alerts." actions={<AddTeamDialog />} />
      {list.kind === 'failed' ? (
        <ListFailed title="Couldn't load teams" message={list.message} onRetry={pages.retry} />
      ) : list.kind === 'listed' && list.items.length === 0 ? (
        <EmptyState icon={UsersRound} title="No teams yet" description="Add the first team with Add team." />
      ) : (
        <Table aria-label="Teams" aria-busy={list.kind === 'loading'}>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Slug</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.kind === 'loading' ? (
              <SkeletonRows columns={COLUMNS} />
            ) : (
              list.items.map((team) => (
                <TableRow key={team.id}>
                  <TableCell className="font-medium">
                    <Link
                      to="/teams/$team/alerts"
                      params={{ team: team.slug }}
                      className="rounded-sm underline-offset-4 hover:text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                    >
                      {team.name}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-[13px]/[20px] text-muted-foreground">{team.slug}</TableCell>
                  <TableCell className="max-w-80 truncate text-muted-foreground">{team.description}</TableCell>
                  <TableCell className="w-10 text-right">
                    <RowActions
                      name={team.name}
                      editLabel="Edit team"
                      deleteLabel="Delete team"
                      onEdit={() => setEditing(team)}
                      onDelete={() => setDeleting(team)}
                    />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
      <ShowMore pages={pages} />
      <EditTeamDialog team={editing} onClose={() => setEditing(null)} />
      <DeleteTeamDialog team={deleting} onClose={() => setDeleting(null)} />
    </div>
  )
}
