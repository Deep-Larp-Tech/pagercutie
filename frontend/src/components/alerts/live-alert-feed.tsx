import { useState } from 'react'
import type { AlertRead } from '@/api/generated/model'
import { useAlertStream } from '@/hooks/use-alert-stream'
import type { AlertFilters } from '@/lib/alert-feed'
import { severityLabel } from '@/lib/severity'
import { AlertFeed, type FeedEmptyState } from './alert-feed'
import { ConnectionBar } from './connection-bar'

/** Props for `LiveAlertFeed`. */
export interface LiveAlertFeedProps {
  /** Team whose alerts to show; omit for every alert the user can see. */
  teamId?: string
  filters: AlertFilters
  empty: FeedEmptyState
  /** Team name per card, for feeds that span teams. */
  teamName?: (alert: AlertRead) => string | undefined
}

interface Announcement {
  text: string
  urgent: boolean
}

/**
 * `AlertFeed` kept live by `useAlertStream`, with its `ConnectionBar` and a screen reader announcer: new critical
 * and error alerts are read out assertively, others politely; counter bumps are not announced (DESIGN.md §9).
 */
export function LiveAlertFeed({ teamId, filters, empty, teamName }: LiveAlertFeedProps) {
  const [announcement, setAnnouncement] = useState<Announcement | null>(null)
  const { query, connection, retry } = useAlertStream({
    teamId,
    filters,
    onAlertCreated: (alert) =>
      setAnnouncement({
        text: `${severityLabel[alert.severity]}: ${alert.title}`,
        urgent: alert.severity === 'critical' || alert.severity === 'error',
      }),
  })
  return (
    <div className="flex flex-col gap-3">
      <ConnectionBar connection={connection} onRetry={retry} />
      <AlertFeed query={query} empty={empty} teamName={teamName} />
      <div aria-live="polite" aria-atomic className="sr-only" data-testid="announcer-polite">
        {announcement !== null && !announcement.urgent ? announcement.text : ''}
      </div>
      <div aria-live="assertive" aria-atomic className="sr-only" data-testid="announcer-assertive">
        {announcement?.urgent === true ? announcement.text : ''}
      </div>
    </div>
  )
}
