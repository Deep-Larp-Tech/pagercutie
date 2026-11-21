import type { ReactNode } from 'react'
import type { AlertRead } from '@/api/generated/model'
import { AlertActions } from '@/components/alerts/alert-card'
import { AlertStatusBar } from '@/components/alerts/alert-status-bar'
import { OccurrenceCounter } from '@/components/alerts/occurrence-counter'
import { RelativeTime } from '@/components/alerts/relative-time'
import { SeverityBadge } from '@/components/alerts/severity-badge'
import { StatusIndicator } from '@/components/alerts/status-indicator'
import { usePersonName } from '@/hooks/use-person-name'
import { useVisibleTeams } from '@/hooks/use-visible-teams'
import { formatFieldValue } from '@/lib/fields'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'
import { alertColourClass } from '@/lib/severity'
import { cn } from '@/lib/utils'
import { PersonNameText } from './person-name'

function Meta({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[12px]/[16px] font-medium text-muted-foreground">{term}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  )
}

/** Props for `AlertSummary`. */
export interface AlertSummaryProps {
  alert: AlertRead
}

/**
 * The top of the alert detail, in the rule's colour (DESIGN.md §5.1): severity, status, counter, the title as the
 * page's `h1`, body and fields, then first and last seen, team, escalations and who responded, with Acknowledge or
 * Resolve for users who may respond.
 */
export function AlertSummary({ alert }: AlertSummaryProps) {
  const me = useMe()
  const { teams } = useVisibleTeams()
  const personName = usePersonName()
  const teamName = (id: string) => teams.find(({ team }) => team.id === id)?.team.name
  // A personal rule's alert (no team) is visible to its owner, who may respond; `can` leaves that call to us.
  const mayRespond = alert.team_id === null || can(me, 'alert.respond', alert)
  const resolved = alert.status === 'resolved'

  const teamText = (id: string) => {
    const name = teamName(id)
    return name === undefined ? (
      <span className="font-mono" title={id}>
        Team {id.slice(0, 8)}
      </span>
    ) : (
      name
    )
  }

  return (
    <header
      className={cn(
        'relative isolate flex flex-col gap-4 overflow-hidden rounded-lg border bg-card py-4 pr-4 pl-6',
        resolved ? 'shadow-none' : 'shadow-card',
        alertColourClass[alert.colour],
      )}
    >
      <AlertStatusBar status={alert.status} occurrences={alert.occurrences} />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <SeverityBadge severity={alert.severity} colour={alert.colour} />
        <StatusIndicator alert={alert} meId={me.user.id} />
        {alert.occurrences > 1 && <OccurrenceCounter count={alert.occurrences} className="ml-auto" />}
      </div>

      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1
            className={cn(
              'text-[24px]/[32px] font-semibold tracking-[-0.02em] transition-colors duration-(--duration-base)',
              resolved && 'text-muted-foreground',
            )}
          >
            {alert.title}
          </h1>
          {alert.body !== null && <p className="whitespace-pre-line text-muted-foreground">{alert.body}</p>}
        </div>
        {mayRespond && <AlertActions alert={alert} />}
      </div>

      {alert.fields.length > 0 && (
        <dl className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-x-3 font-mono text-[13px]/[20px] font-[450]">
          {alert.fields.map((field) => (
            <div key={field.path} className="contents">
              <dt className="text-muted-foreground">{field.path}</dt>
              <dd className={cn('break-all', resolved ? 'text-muted-foreground' : 'text-c-text')}>
                {formatFieldValue(field.value)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border-t pt-4 sm:grid-cols-3 lg:grid-cols-4">
        <Meta term="First seen">
          <RelativeTime value={alert.first_seen_at} timeZone={me.user.timezone} />
        </Meta>
        <Meta term="Last seen">
          <RelativeTime value={alert.last_seen_at} timeZone={me.user.timezone} />
        </Meta>
        <Meta term="Team">{alert.team_id === null ? 'Personal rule' : teamText(alert.team_id)}</Meta>
        {alert.escalated_team_ids.length > 0 && (
          <Meta term="Escalated to">
            <ul className="flex flex-col">
              {alert.escalated_team_ids.map((id) => (
                <li key={id}>{teamText(id)}</li>
              ))}
            </ul>
          </Meta>
        )}
        {alert.acknowledged_by !== null && (
          <Meta term="Acknowledged by">
            <PersonNameText person={personName(alert.acknowledged_by)} />
          </Meta>
        )}
        {alert.status === 'resolved' && (
          <Meta term="Resolved by">
            {alert.resolved_by === null ? (
              'PagerCutie, automatically'
            ) : (
              <PersonNameText person={personName(alert.resolved_by)} />
            )}
          </Meta>
        )}
      </dl>
    </header>
  )
}
