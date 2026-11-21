import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { KeyRound, MoreHorizontal, Pencil, Plug, Trash2 } from 'lucide-react'
import type { SourceRead } from '@/api/generated/model'
import {
  getListSourcesQueryKey,
  listSources,
  useUpdateSource,
  type listSourcesResponse,
} from '@/api/generated/sources/sources'
import { ListFailed, ShowMore, SkeletonRows } from '@/components/admin/list-parts'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { Button } from '@/components/ui/button'
import { CopyButton } from '@/components/ui/copy-button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { unexpectedStatusMessage } from '@/lib/api'
import { sourceTypeLabel } from '@/lib/ingest-example'
import { OFFLINE, useOffsetPages, type PageResult } from '@/lib/pagination'
import { DeleteSourceDialog } from './delete-source-dialog'
import { AddSourceDialog, EditSourceDialog } from './source-dialogs'
import { CreateTokenDialog, RotateTokenDialog } from './token-dialogs'
import { READ_ONLY_NOTICE, useTeamConfig } from './use-team-config'

/** Reads one `GET /sources` page. */
function readSourcesPage(response: listSourcesResponse): PageResult<SourceRead> {
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

/** `/teams/$team/sources`: the systems that send the team events (`ING-1`); members and leads manage them. */
export function SourcesPage() {
  const { team, canEdit } = useTeamConfig()
  const params = { team_id: team.id }
  const pages = useOffsetPages(
    [...getListSourcesQueryKey(params), 'pages'],
    (page, signal) => listSources({ ...params, ...page }, { signal }),
    readSourcesPage,
  )
  const [editing, setEditing] = useState<SourceRead | null>(null)
  // The row as clicked: its `has_token` picks the create or the rotate dialog and stays put while the list reloads.
  const [tokenFor, setTokenFor] = useState<SourceRead | null>(null)
  const [deleting, setDeleting] = useState<SourceRead | null>(null)
  const [switchError, setSwitchError] = useState<string | null>(null)
  const { list } = pages
  const columns = canEdit ? 7 : 6

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Sources"
        description="Systems that send events to this team. Each one has an ingest URL and accepts events once it has a secret token."
        actions={canEdit ? <AddSourceDialog team={team} /> : undefined}
      />
      {!canEdit && <p className="text-muted-foreground">{READ_ONLY_NOTICE}</p>}
      {switchError !== null && (
        <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
          {switchError}
        </p>
      )}
      {list.kind === 'failed' ? (
        <ListFailed title="Couldn't load sources" message={list.message} onRetry={pages.retry} />
      ) : list.kind === 'listed' && list.items.length === 0 ? (
        <EmptyState
          icon={Plug}
          title="No sources yet"
          description={
            canEdit
              ? 'Add a source with New source, then send events to its ingest URL.'
              : 'Members and leads add the systems that send events here.'
          }
        />
      ) : (
        <Table aria-label="Sources" aria-busy={list.kind === 'loading'}>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Slug</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Ingest URL</TableHead>
              <TableHead>Token</TableHead>
              <TableHead>Enabled</TableHead>
              {canEdit && (
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.kind === 'loading' ? (
              <SkeletonRows columns={columns} />
            ) : (
              list.items.map((source) => (
                <TableRow key={source.id}>
                  <TableCell className="font-medium">{source.name}</TableCell>
                  <TableCell className="font-mono text-[13px]/[20px] whitespace-nowrap text-muted-foreground">{source.slug}</TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{sourceTypeLabel[source.type]}</TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1 whitespace-nowrap">
                      <span className="font-mono text-[13px]/[20px]">{source.ingest_url}</span>
                      <CopyButton value={source.ingest_url} label={`Copy ingest URL of ${source.name}`} />
                    </span>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    <TokenStatus source={source} canEdit={canEdit} onCreate={() => setTokenFor(source)} />
                  </TableCell>
                  <TableCell>
                    {canEdit ? (
                      <EnabledSwitch source={source} onError={setSwitchError} />
                    ) : (
                      <span className="text-muted-foreground">{source.enabled ? 'On' : 'Off'}</span>
                    )}
                  </TableCell>
                  {canEdit && (
                    <TableCell className="w-10 text-right">
                      <SourceRowActions
                        name={source.name}
                        hasToken={source.has_token}
                        onEdit={() => setEditing(source)}
                        onToken={() => setTokenFor(source)}
                        onDelete={() => setDeleting(source)}
                      />
                    </TableCell>
                  )}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
      <ShowMore pages={pages} />
      <EditSourceDialog source={editing} team={team} onClose={() => setEditing(null)} />
      <CreateTokenDialog source={tokenFor?.has_token === false ? tokenFor : null} onClose={() => setTokenFor(null)} />
      <RotateTokenDialog source={tokenFor?.has_token === true ? tokenFor : null} onClose={() => setTokenFor(null)} />
      <DeleteSourceDialog source={deleting} onClose={() => setDeleting(null)} />
    </div>
  )
}

/** Whether the source has an ingest token; without one ingest answers `404`, so editors get **Create token** here. */
function TokenStatus({ source, canEdit, onCreate }: { source: SourceRead; canEdit: boolean; onCreate: () => void }) {
  if (source.has_token) return <span className="text-muted-foreground">Set</span>
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-muted-foreground">No token yet</span>
      {canEdit && (
        <Button variant="secondary" size="sm" aria-label={`Create token for ${source.name}`} onClick={onCreate}>
          Create token
        </Button>
      )}
    </span>
  )
}

/** Turns a source on or off (`PATCH /sources/{id}` with `enabled`); a failure goes to the page's error line. */
function EnabledSwitch({ source, onError }: { source: SourceRead; onError: (message: string | null) => void }) {
  const queryClient = useQueryClient()
  const update = useUpdateSource()

  async function toggle(enabled: boolean) {
    onError(null)
    const response = await update.mutateAsync({ sourceId: source.id, data: { enabled } }).catch(() => null)
    const action = enabled ? 'turn on' : 'turn off'
    if (response === null) {
      onError(OFFLINE)
      return
    }
    switch (response.status) {
      case 200:
        await queryClient.invalidateQueries({ queryKey: getListSourcesQueryKey() })
        return
      case 403:
        onError(`Couldn't ${action} ${source.name}. Only members and leads can change sources.`)
        return
      case 404:
        await queryClient.invalidateQueries({ queryKey: getListSourcesQueryKey() })
        onError(`Couldn't ${action} ${source.name}. It no longer exists.`)
        return
      case 400:
      case 422:
        onError(`Couldn't ${action} ${source.name}. Reload the page and try again.`)
        return
      case 401:
        return
      default:
        onError(`Couldn't ${action} ${source.name}. ${unexpectedStatusMessage(response)}`)
    }
  }

  return (
    <Switch
      aria-label={`Accept events from ${source.name}`}
      checked={update.isPending ? update.variables.data.enabled === true : source.enabled}
      disabled={update.isPending}
      onCheckedChange={(enabled) => void toggle(enabled)}
    />
  )
}

interface SourceRowActionsProps {
  name: string
  /** Picks **Rotate token** over **Create token**. */
  hasToken: boolean
  onEdit: () => void
  onToken: () => void
  onDelete: () => void
}

function SourceRowActions({ name, hasToken, onEdit, onToken, onDelete }: SourceRowActionsProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${name}`} />}>
        <MoreHorizontal strokeWidth={1.75} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={onEdit}>
          <Pencil strokeWidth={1.75} />
          Edit source
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onToken}>
          <KeyRound strokeWidth={1.75} />
          {hasToken ? 'Rotate token' : 'Create token'}
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" onClick={onDelete}>
          <Trash2 strokeWidth={1.75} />
          Delete source
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
