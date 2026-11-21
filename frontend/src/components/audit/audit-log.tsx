import { Fragment, useId, useState, type ReactNode } from 'react'
import { Link } from '@tanstack/react-router'
import { ChevronDown, History, ListFilter } from 'lucide-react'
import { getListAuditEntriesQueryKey, listAuditEntries, type listAuditEntriesResponse } from '@/api/generated/audit/audit'
import type { AuditEntryRead, MeRead, TeamRead } from '@/api/generated/model'
import { ListFailed, ShowMore, SkeletonRows } from '@/components/admin/list-parts'
import { AuditFilterBar } from '@/components/audit/audit-filters'
import { RelativeTime } from '@/components/alerts/relative-time'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { Button } from '@/components/ui/button'
import { buttonVariants, focusRing } from '@/components/ui/styles'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useVisibleTeams } from '@/hooks/use-visible-teams'
import { unexpectedStatusMessage } from '@/lib/api'
import { auditActionText, auditQuery, entityTypeLabel, isFiltered, type AuditFilters } from '@/lib/audit'
import { useOffsetPages, type PageResult } from '@/lib/pagination'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'
import type { VisibleTeam } from '@/lib/teams'
import { cn } from '@/lib/utils'

const COLUMNS = 5

/** First block of a UUID, enough to tell entries apart on screen; the full id is in the title and the filter. */
function shortId(id: string): string {
  return id.slice(0, 8)
}

/** Reads one `GET /audit` page. */
function readAuditPage(response: listAuditEntriesResponse): PageResult<AuditEntryRead> {
  switch (response.status) {
    case 200:
      return { kind: 'items', items: response.data }
    case 401:
      return { kind: 'silent' }
    case 422:
      return { kind: 'failed', message: "The filters aren't valid. Clear them and try again." }
    default:
      return { kind: 'failed', message: unexpectedStatusMessage(response) }
  }
}

/** Props for `AuditLogPage`. */
export interface AuditLogPageProps {
  /** Team whose entries to list; omit for every entry (admins, `/admin/audit`). */
  team?: TeamRead
  filters: AuditFilters
  /** Called with new filters; the route writes them to the address. */
  onFiltersChange: (filters: AuditFilters) => void
}

/**
 * The audit log (`RUN-5`): who did what to which entity, newest first, 100 entries per page with **Show more**,
 * filtered by time range, entity type, action, who did it, team (admin page) and entity id. A team's page lists that
 * team's entries; the admin page lists every entry.
 */
export function AuditLogPage({ team, filters: addressFilters, onFiltersChange }: AuditLogPageProps) {
  const filters =
    team === undefined ? addressFilters : { ...addressFilters, team_id: undefined, without_team: undefined }
  const [anchor, setAnchor] = useState(() => Date.now())
  const changeFilters = (next: AuditFilters) => {
    if (next.range !== filters.range) setAnchor(Date.now())
    onFiltersChange(next)
  }
  const params = auditQuery(filters, team?.id, anchor)
  const pages = useOffsetPages(
    [...getListAuditEntriesQueryKey(), 'pages', params],
    (page, signal) => listAuditEntries({ ...params, ...page }, { signal }),
    readAuditPage,
  )
  const { list } = pages
  const filtered = isFiltered(filters)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Audit log"
        description={
          team === undefined
            ? 'Who did what in every team, newest first.'
            : `Who did what in ${team.name}, newest first.`
        }
      />
      <AuditFilterBar filters={filters} onChange={changeFilters} team={team} />
      {list.kind === 'failed' ? (
        <ListFailed title="Couldn't load the audit log" message={list.message} onRetry={pages.retry} />
      ) : list.kind === 'listed' && list.items.length === 0 ? (
        filtered ? (
          <EmptyState
            icon={ListFilter}
            title="No entries match these filters"
            description="Change or clear the filters to see more of the log."
            action={
              <Button variant="secondary" onClick={() => onFiltersChange({})}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={History}
            title="Nothing recorded yet"
            description="Acknowledgements, resolutions, runbook decisions and configuration changes show up here."
          />
        )
      ) : (
        <Table aria-label="Audit log" aria-busy={list.kind === 'loading'}>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Who</TableHead>
              <TableHead>What</TableHead>
              <TableHead>Entity</TableHead>
              <TableHead>
                <span className="sr-only">Details</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.kind === 'loading' ? (
              <SkeletonRows columns={COLUMNS} />
            ) : (
              list.items.map((entry) => <AuditRow key={entry.id} entry={entry} team={team} />)
            )}
          </TableBody>
        </Table>
      )}
      <ShowMore pages={pages} />
    </div>
  )
}

/** One entry, with its `data` behind a disclosure button as formatted JSON. */
function AuditRow({ entry, team }: { entry: AuditEntryRead; team: TeamRead | undefined }) {
  const me = useMe()
  const [open, setOpen] = useState(false)
  const detailsId = useId()
  const hasData = Object.keys(entry.data).length > 0

  return (
    <Fragment>
      <TableRow className={cn(open && 'border-b-0')}>
        <TableCell className="whitespace-nowrap">
          <RelativeTime value={entry.at} timeZone={me.user.timezone} />
        </TableCell>
        <TableCell>
          {entry.actor_user_id === null ? (
            <span className="text-muted-foreground">System</span>
          ) : entry.actor_user_id === me.user.id ? (
            'You'
          ) : entry.actor_name !== undefined && entry.actor_name !== null ? (
            entry.actor_name
          ) : (
            <span className="font-mono text-[13px]/[20px]" title={entry.actor_user_id}>
              User {shortId(entry.actor_user_id)}
            </span>
          )}
        </TableCell>
        <TableCell className="font-medium">{auditActionText(entry.action)}</TableCell>
        <TableCell>
          <EntityCell entry={entry} team={team} />
        </TableCell>
        <TableCell className="w-10 text-right">
          {hasData && (
            <Button
              variant="ghost"
              size="icon-sm"
              aria-expanded={open}
              aria-controls={detailsId}
              aria-label={`${open ? 'Hide' : 'Show'} details of ${auditActionText(entry.action)}`}
              onClick={() => setOpen((current) => !current)}
            >
              <ChevronDown
                strokeWidth={1.75}
                className={cn('transition-transform duration-(--duration-fast) ease-standard', open && 'rotate-180')}
              />
            </Button>
          )}
        </TableCell>
      </TableRow>
      {open && (
        <TableRow id={detailsId}>
          <TableCell colSpan={COLUMNS} className="h-auto pb-3">
            <pre className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-[13px]/[20px] font-[450]">
              {JSON.stringify(entry.data, null, 2)}
            </pre>
          </TableCell>
        </TableRow>
      )}
    </Fragment>
  )
}

/** The entity's type in words, a link to its page where one exists, and its id, which filters the log to it. */
function EntityCell({ entry, team }: { entry: AuditEntryRead; team: TeamRead | undefined }) {
  const me = useMe()
  const { teams } = useVisibleTeams()
  const label = entityTypeLabel(entry.entity_type)
  const page = entityPage(entry, teams, me)
  const history = { entity_type: entry.entity_type, entity_id: entry.entity_id }
  const historyLabel = `Show the history of ${label.toLowerCase()} ${entry.entity_id}`
  const linkClass = cn('rounded-sm font-mono text-[13px]/[20px] text-muted-foreground hover:text-foreground', focusRing)

  return (
    <span className="flex flex-wrap items-center gap-x-2">
      {page ?? <span>{label}</span>}
      {team === undefined ? (
        <Link to="/admin/audit" search={history} aria-label={historyLabel} title={entry.entity_id} className={linkClass}>
          {shortId(entry.entity_id)}
        </Link>
      ) : (
        <Link
          to="/teams/$team/audit"
          params={{ team: team.slug }}
          search={history}
          aria-label={historyLabel}
          title={entry.entity_id}
          className={linkClass}
        >
          {shortId(entry.entity_id)}
        </Link>
      )}
    </span>
  )
}

/**
 * A link to the page that shows the entity, for the entity types that have one; `null` otherwise. Rules, runbooks and
 * sources open their team's list, since their detail pages are not built yet.
 */
function entityPage(entry: AuditEntryRead, teams: readonly VisibleTeam[], me: MeRead): ReactNode {
  const label = entityTypeLabel(entry.entity_type)
  const className = cn(buttonVariants({ variant: 'ghost', size: 'sm' }), '-mx-2.5')
  const slugOf = (id: string | null) => (id === null ? undefined : teams.find(({ team }) => team.id === id)?.team.slug)
  const owner = slugOf(entry.team_id)
  switch (entry.entity_type) {
    case 'team': {
      const slug = slugOf(entry.entity_id)
      return slug === undefined ? null : (
        <Link to="/teams/$team/alerts" params={{ team: slug }} className={className}>
          {label}
        </Link>
      )
    }
    case 'alert':
      return owner === undefined ? null : (
        <Link to="/teams/$team/alerts" params={{ team: owner }} className={className}>
          {label}
        </Link>
      )
    case 'rule':
      return owner === undefined ? null : (
        <Link to="/teams/$team/rules" params={{ team: owner }} className={className}>
          {label}
        </Link>
      )
    case 'runbook':
      return owner === undefined ? null : (
        <Link to="/teams/$team/runbooks" params={{ team: owner }} className={className}>
          {label}
        </Link>
      )
    case 'source':
      return owner === undefined ? null : (
        <Link to="/teams/$team/sources" params={{ team: owner }} className={className}>
          {label}
        </Link>
      )
    case 'user':
      return can(me, 'users-and-teams.manage') ? (
        <Link to="/admin/users" className={className}>
          {label}
        </Link>
      ) : null
    default:
      return null
  }
}
