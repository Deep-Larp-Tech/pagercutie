import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { TriangleAlert } from 'lucide-react'
import type { RunbookRead } from '@/api/generated/model'
import { getGetRunbookQueryOptions } from '@/api/generated/runbooks/runbooks'
import { RelativeTime } from '@/components/alerts/relative-time'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { buttonVariants } from '@/components/ui/styles'
import { unexpectedStatusMessage } from '@/lib/api'
import { OFFLINE } from '@/lib/pagination'
import { runbookFormatInfo } from '@/lib/runbooks'
import { LOAD_REJECTED, READ_ONLY, RUNBOOK_GONE } from './messages'
import { ParsedRunbook } from './parse-preview'
import { RunbookEditor } from './runbook-editor'
import { useRunbookScope } from './use-runbook-scope'

/**
 * `/teams/$team/runbooks/$runbookId`: loads the runbook (`GET /runbooks/{id}`) and shows the editor to members and
 * leads, the saved text and steps to everyone else.
 */
export function RunbookPage({ runbookId }: { runbookId: string }) {
  const { team, canEdit } = useRunbookScope()
  const query = useQuery(getGetRunbookQueryOptions(runbookId))

  if (query.isPending) return <RunbookSkeleton />
  if (query.isError) return <RunbookError message={OFFLINE} onRetry={() => void query.refetch()} />
  const response = query.data
  switch (response.status) {
    case 200:
      // A runbook of another team, reached by editing the URL, is not shown under this team.
      if (response.data.team_id !== team.id) return <RunbookError message={RUNBOOK_GONE} />
      return canEdit ? (
        <RunbookEditor key={response.data.id} runbook={response.data} />
      ) : (
        <RunbookReadOnly runbook={response.data} />
      )
    case 401:
      return null
    case 404:
      return <RunbookError message={RUNBOOK_GONE} />
    case 422:
      return <RunbookError message={LOAD_REJECTED} />
    default:
      return <RunbookError message={unexpectedStatusMessage(response)} onRetry={() => void query.refetch()} />
  }
}

function RunbookSkeleton() {
  return (
    <div className="flex flex-col gap-6" data-testid="runbook-skeleton">
      <Skeleton className="h-8 w-64" />
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-8 w-full" />
          ))}
          <Skeleton className="h-64 w-full" />
        </div>
        <Skeleton className="h-80 w-full" />
      </div>
    </div>
  )
}

function RunbookError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { team } = useRunbookScope()
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Runbook" />
      <EmptyState
        icon={TriangleAlert}
        role="alert"
        title="Couldn't open this runbook"
        description={message}
        action={
          onRetry !== undefined ? (
            <Button variant="secondary" onClick={onRetry}>
              Try again
            </Button>
          ) : (
            <Link to="/teams/$team/runbooks" params={{ team: team.slug }} className={buttonVariants({ variant: 'secondary' })}>
              Back to runbooks
            </Link>
          )
        }
      />
    </div>
  )
}

/** A runbook for someone who may read but not change it: details, original text and saved steps. */
function RunbookReadOnly({ runbook }: { runbook: RunbookRead }) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={runbook.title} />
      <p className="text-muted-foreground">{READ_ONLY}</p>
      <div className="grid items-start gap-8 lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-5">
          <dl className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-3">
            <dt className="text-muted-foreground">Slug</dt>
            <dd className="font-mono text-[13px]/[20px] font-[450]">{runbook.slug}</dd>
            <dt className="text-muted-foreground">Format</dt>
            <dd>{runbookFormatInfo[runbook.format].label}</dd>
            <dt className="text-muted-foreground">Updated</dt>
            <dd>
              <RelativeTime value={runbook.updated_at} />
            </dd>
          </dl>
          <section aria-labelledby="runbook-text-title" className="flex flex-col gap-2">
            <h2 id="runbook-text-title" className="text-[18px]/[26px] font-semibold tracking-[-0.01em]">
              Runbook text
            </h2>
            <pre className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-[13px]/[20px] font-[450] whitespace-pre-wrap">
              {runbook.original}
            </pre>
          </section>
        </div>
        <section aria-labelledby="runbook-steps-title" className="flex min-w-0 flex-col gap-4 rounded-xl border p-4">
          <h2 id="runbook-steps-title" className="text-[18px]/[26px] font-semibold tracking-[-0.01em]">
            Steps
          </h2>
          <ParsedRunbook result={{ attach: runbook.attach, steps: runbook.steps, warnings: [] }} />
        </section>
      </div>
    </div>
  )
}
