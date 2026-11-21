import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { BellOff, TriangleAlert, type LucideIcon } from 'lucide-react'
import type { ListAlertsQueryError, listAlertsResponse } from '@/api/generated/alerts/alerts'
import type { AlertRead } from '@/api/generated/model'
import { EmptyState } from '@/components/shell/empty-state'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { unexpectedStatusMessage } from '@/lib/api'
import { motionTokens } from '@/lib/motion'
import { AlertCard } from './alert-card'

/** What an empty feed says, and the one action that fills it. */
export interface FeedEmptyState {
  icon?: LucideIcon
  title: string
  description: string
  action?: ReactNode
}

/** Props for `AlertFeed`. */
export interface AlertFeedProps {
  /** The `GET /alerts` query from `useAlertStream`. */
  query: UseQueryResult<listAlertsResponse, ListAlertsQueryError>
  empty: FeedEmptyState
  /** Team name to show on each card, for feeds that span teams; omit inside one team. */
  teamName?: (alert: AlertRead) => string | undefined
}

function FeedSkeleton() {
  return (
    <div role="status" aria-label="Loading alerts" className="flex flex-col gap-3">
      {[0, 1, 2].map((index) => (
        <div key={index} className="flex flex-col gap-2 rounded-lg border bg-card py-3 pr-3 pl-5 shadow-card">
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-20 rounded-full" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="ml-auto h-4 w-24" />
          </div>
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      ))}
    </div>
  )
}

function FeedError({ description, onRetry }: { description: string; onRetry?: () => void }) {
  return (
    <EmptyState
      icon={TriangleAlert}
      role="alert"
      title="Couldn't load alerts"
      description={description}
      action={
        onRetry === undefined ? undefined : (
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        )
      }
    />
  )
}

function FeedList({ alerts, empty, teamName }: { alerts: AlertRead[] } & Omit<AlertFeedProps, 'query'>) {
  const reduceMotion = useReducedMotion() === true
  return (
    <>
      <ul className="flex flex-col gap-3" aria-label="Alerts">
        <AnimatePresence initial={false}>
          {alerts.map((alert) => (
            <motion.li
              key={alert.id}
              layout={reduceMotion ? false : 'position'}
              initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, transition: reduceMotion ? motionTokens.fast : motionTokens.exit }}
              transition={reduceMotion ? motionTokens.fast : motionTokens.spring}
            >
              <AlertCard alert={alert} teamName={teamName?.(alert)} />
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
      {alerts.length === 0 && (
        <EmptyState
          icon={empty.icon ?? BellOff}
          title={empty.title}
          description={empty.description}
          action={empty.action}
        />
      )}
    </>
  )
}

/**
 * A list of `AlertCard`s with its loading (three skeleton cards), empty and error states (DESIGN.md §9). New alerts
 * slide in, the rest shift with `layout`, and leaving alerts fade out.
 */
export function AlertFeed({ query, empty, teamName }: AlertFeedProps) {
  if (query.isPending) return <FeedSkeleton />
  if (query.isError) {
    return (
      <FeedError
        description="Check your connection and try again."
        onRetry={() => void query.refetch()}
      />
    )
  }
  const response = query.data
  switch (response.status) {
    case 200:
      return <FeedList alerts={response.data} empty={empty} teamName={teamName} />
    case 401:
      return null
    case 422:
      return <FeedError description="The filters in the address aren't valid. Clear them and try again." />
    default:
      return <FeedError description={unexpectedStatusMessage(response)} onRetry={() => void query.refetch()} />
  }
}
