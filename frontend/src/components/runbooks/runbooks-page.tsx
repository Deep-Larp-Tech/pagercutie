import { Link } from '@tanstack/react-router'
import { BookOpen } from 'lucide-react'
import type { RunbookRead } from '@/api/generated/model'
import { getListRunbooksQueryKey, listRunbooks, type listRunbooksResponse } from '@/api/generated/runbooks/runbooks'
import { ListFailed, ShowMore, SkeletonRows } from '@/components/admin/list-parts'
import { RelativeTime } from '@/components/alerts/relative-time'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { buttonVariants } from '@/components/ui/styles'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { unexpectedStatusMessage } from '@/lib/api'
import { useOffsetPages, type PageResult } from '@/lib/pagination'
import { describeCondition, runbookFormatInfo } from '@/lib/runbooks'
import { approvalCount } from '@/lib/steps'
import { READ_ONLY } from './messages'
import { useRunbookScope } from './use-runbook-scope'

const COLUMNS = 7

/** Reads one `GET /runbooks` page. */
function readRunbooksPage(response: listRunbooksResponse): PageResult<RunbookRead> {
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

/** `/teams/$team/runbooks`: the team's runbooks (`GET /runbooks?team_id=`); members and leads add new ones. */
export function RunbooksPage() {
  const { team, canEdit } = useRunbookScope()
  const params = { team_id: team.id }
  const pages = useOffsetPages(
    [...getListRunbooksQueryKey(params), 'pages'],
    (page, signal) => listRunbooks({ ...params, ...page }, { signal }),
    readRunbooksPage,
  )
  const { list } = pages

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Runbooks"
        description="What to do when an alert fires. Paste YAML, Markdown, free text or a link."
        actions={
          canEdit ? (
            <Link to="/teams/$team/runbooks/new" params={{ team: team.slug }} className={buttonVariants()}>
              New runbook
            </Link>
          ) : undefined
        }
      />
      {!canEdit && <p className="text-muted-foreground">{READ_ONLY}</p>}
      {list.kind === 'failed' ? (
        <ListFailed title="Couldn't load runbooks" message={list.message} onRetry={pages.retry} />
      ) : list.kind === 'listed' && list.items.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="No runbooks yet"
          description={
            canEdit
              ? 'Add one with New runbook. Rules that name it show its steps on their alerts.'
              : 'Members and leads of the team add runbooks here.'
          }
        />
      ) : (
        <Table aria-label="Runbooks" aria-busy={list.kind === 'loading'}>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Slug</TableHead>
              <TableHead>Format</TableHead>
              <TableHead className="text-right">Steps</TableHead>
              <TableHead className="text-right">Need approval</TableHead>
              <TableHead>Applies when</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.kind === 'loading' ? (
              <SkeletonRows columns={COLUMNS} />
            ) : (
              list.items.map((runbook) => <RunbookRow key={runbook.id} runbook={runbook} team={team.slug} />)
            )}
          </TableBody>
        </Table>
      )}
      <ShowMore pages={pages} />
    </div>
  )
}

function RunbookRow({ runbook, team }: { runbook: RunbookRead; team: string }) {
  const condition = runbook.attach === null ? null : describeCondition(runbook.attach)
  return (
    <TableRow>
      <TableCell className="font-medium">
        <Link
          to="/teams/$team/runbooks/$runbookId"
          params={{ team, runbookId: runbook.id }}
          className="rounded-sm underline-offset-4 hover:text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {runbook.title}
        </Link>
      </TableCell>
      <TableCell className="font-mono text-[13px]/[20px] text-muted-foreground">{runbook.slug}</TableCell>
      <TableCell>{runbookFormatInfo[runbook.format].label}</TableCell>
      <TableCell className="text-right font-mono text-[13px]/[20px] tabular-nums">{runbook.steps.length}</TableCell>
      <TableCell className="text-right font-mono text-[13px]/[20px] tabular-nums">
        {approvalCount(runbook.steps)}
      </TableCell>
      <TableCell className="max-w-64 truncate font-mono text-[13px]/[20px]" title={condition ?? undefined}>
        {condition ?? <span className="font-sans text-muted-foreground">Through rules</span>}
      </TableCell>
      <TableCell>
        <RelativeTime value={runbook.updated_at} />
      </TableCell>
    </TableRow>
  )
}
