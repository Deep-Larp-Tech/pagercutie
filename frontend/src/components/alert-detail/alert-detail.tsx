import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { BellOff, History, ListChecks, TriangleAlert } from 'lucide-react'
import {
  getGetRunbookRunQueryKey,
  getListAlertDeliveriesQueryKey,
  useGetAlert,
  useGetRunbookRun,
  useListAlertDeliveries,
} from '@/api/generated/alerts/alerts'
import { getListAuditEntriesQueryKey, useListAuditEntries } from '@/api/generated/audit/audit'
import type { AlertRead } from '@/api/generated/model'
import { EmptyState } from '@/components/shell/empty-state'
import { NotFoundPage } from '@/components/shell/not-found-page'
import { Section, SectionError } from '@/components/team-settings/section'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useLiveAlert } from '@/hooks/use-live-alert'
import { unexpectedStatusMessage } from '@/lib/api'
import { AlertHistory } from './alert-history'
import { AlertSummary } from './alert-summary'
import { DeliveryTable } from './delivery-table'
import { StepList } from './step-list'

/** Largest page `GET /audit` allows; the history shows at most this many entries. */
export const HISTORY_LIMIT = 100

const offline = 'Check your connection and try again.'
const gone = "This alert no longer exists, or you can't see it any more."

function RowsSkeleton({ label, rows }: { label: string; rows: number }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-3">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-12 w-full" />
      ))}
    </div>
  )
}

function RunbookSection({ alert }: { alert: AlertRead }) {
  const query = useGetRunbookRun(alert.id)
  const retry = () => void query.refetch()
  let content
  if (query.isPending) content = <RowsSkeleton label="Loading runbook steps" rows={3} />
  else if (query.isError) content = <SectionError message={`Couldn't load the runbook. ${offline}`} onRetry={retry} />
  else {
    const response = query.data
    switch (response.status) {
      case 200:
        content =
          response.data === null ? (
            <EmptyState
              icon={ListChecks}
              title="No runbook for this alert"
              description="The rule that fired it has no runbook attached, so there are no steps to run."
            />
          ) : (
            <StepList alert={alert} steps={response.data.steps} />
          )
        break
      case 401:
        content = null
        break
      case 404:
        content = <SectionError message={gone} />
        break
      case 422:
        content = <SectionError message="This alert's address isn't valid. Open it again from a feed." />
        break
      default:
        content = <SectionError message={unexpectedStatusMessage(response)} onRetry={retry} />
    }
  }
  return (
    <Section title="Runbook" description="What PagerCutie does about this alert, step by step.">
      {content}
    </Section>
  )
}

function DeliveriesSection({ alertId }: { alertId: string }) {
  const query = useListAlertDeliveries(alertId)
  const retry = () => void query.refetch()
  let content
  if (query.isPending) content = <RowsSkeleton label="Loading deliveries" rows={2} />
  else if (query.isError) {
    content = <SectionError message={`Couldn't load the deliveries. ${offline}`} onRetry={retry} />
  } else {
    const response = query.data
    switch (response.status) {
      case 200:
        content =
          response.data.length === 0 ? (
            <EmptyState
              icon={BellOff}
              title="Nobody was notified"
              description="The alert shows in the feed only: its rule notifies no one, or their preferences say UI only."
            />
          ) : (
            <DeliveryTable deliveries={response.data} />
          )
        break
      case 401:
        content = null
        break
      case 404:
        content = <SectionError message={gone} />
        break
      case 422:
        content = <SectionError message="This alert's address isn't valid. Open it again from a feed." />
        break
      default:
        content = <SectionError message={unexpectedStatusMessage(response)} onRetry={retry} />
    }
  }
  return (
    <Section title="Deliveries" description="Who was notified, on which channel, and whether it arrived.">
      {content}
    </Section>
  )
}

function HistorySection({ alertId }: { alertId: string }) {
  const query = useListAuditEntries({ entity_type: 'alert', entity_id: alertId, limit: HISTORY_LIMIT })
  const retry = () => void query.refetch()
  let content
  if (query.isPending) content = <RowsSkeleton label="Loading history" rows={3} />
  else if (query.isError) content = <SectionError message={`Couldn't load the history. ${offline}`} onRetry={retry} />
  else {
    const response = query.data
    switch (response.status) {
      case 200:
        content =
          response.data.length === 0 ? (
            <EmptyState
              icon={History}
              title="No history yet"
              description="Actions on this alert, by people and by PagerCutie, show up here."
            />
          ) : (
            <AlertHistory entries={response.data} />
          )
        break
      case 401:
        content = null
        break
      case 422:
        content = <SectionError message="Couldn't load the history. Reload the page and try again." />
        break
      default:
        content = <SectionError message={unexpectedStatusMessage(response)} onRetry={retry} />
    }
  }
  return (
    <Section title="History" description="What was done to this alert and by whom, newest first.">
      {content}
    </Section>
  )
}

function LoadedAlert({ fetched }: { fetched: AlertRead }) {
  const alert = useLiveAlert(fetched)
  const queryClient = useQueryClient()
  // A live change to the alert (another occurrence, an acknowledgement, an escalation) can move its runbook, add
  // deliveries and audit entries; none of those has a stream, so they reload.
  const change = `${alert.status}|${alert.occurrences}|${alert.escalated_team_ids.length}`
  const previous = useRef(change)
  useEffect(() => {
    if (previous.current === change) return
    previous.current = change
    void queryClient.invalidateQueries({ queryKey: getGetRunbookRunQueryKey(alert.id), exact: true })
    void queryClient.invalidateQueries({ queryKey: getListAlertDeliveriesQueryKey(alert.id), exact: true })
    void queryClient.invalidateQueries({ queryKey: getListAuditEntriesQueryKey() })
  }, [change, alert.id, queryClient])

  return (
    <div className="flex flex-col gap-8">
      <AlertSummary alert={alert} />
      <RunbookSection alert={alert} />
      <DeliveriesSection alertId={alert.id} />
      <HistorySection alertId={alert.id} />
    </div>
  )
}

function DetailSkeleton() {
  return (
    <div role="status" aria-label="Loading alert" className="flex flex-col gap-4 rounded-lg border bg-card p-4">
      <div className="flex items-center gap-3">
        <Skeleton className="h-5 w-20 rounded-full" />
        <Skeleton className="h-4 w-16" />
      </div>
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-10 w-full" />
    </div>
  )
}

/** Props for `AlertDetail`. */
export interface AlertDetailProps {
  alertId: string
}

/**
 * The alert detail (`RUN-2`–`RUN-5`, `DEL-6`): the alert, its runbook steps with their decisions, its deliveries and
 * its history. An alert that does not exist or is hidden shows the 404 page inside the shell.
 */
export function AlertDetail({ alertId }: AlertDetailProps) {
  const query = useGetAlert(alertId)
  if (query.isPending) return <DetailSkeleton />
  if (query.isError) {
    return (
      <EmptyState
        icon={TriangleAlert}
        role="alert"
        title="Couldn't load the alert"
        description={offline}
        action={
          <Button variant="secondary" onClick={() => void query.refetch()}>
            Try again
          </Button>
        }
      />
    )
  }
  const response = query.data
  switch (response.status) {
    case 200:
      return <LoadedAlert key={response.data.id} fetched={response.data} />
    case 401:
      // The session ended; the sign-in redirect is under way (ADR-0052).
      return null
    case 404:
    case 422:
      return <NotFoundPage />
    default:
      return (
        <EmptyState
          icon={TriangleAlert}
          role="alert"
          title="Couldn't load the alert"
          description={unexpectedStatusMessage(response)}
          action={
            <Button variant="secondary" onClick={() => void query.refetch()}>
              Try again
            </Button>
          }
        />
      )
  }
}
