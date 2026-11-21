import { useId } from 'react'
import { Link } from '@tanstack/react-router'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import type { AlertRead } from '@/api/generated/model'
import { Button } from '@/components/ui/button'
import { focusRing } from '@/components/ui/styles'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useAlertResponse } from '@/hooks/use-alert-response'
import { formatFieldValue } from '@/lib/fields'
import { motionTokens } from '@/lib/motion'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'
import { alertColourClass } from '@/lib/severity'
import { cn } from '@/lib/utils'
import { AlertStatusBar } from './alert-status-bar'
import { OccurrenceCounter } from './occurrence-counter'
import { RelativeTime } from './relative-time'
import { SeverityBadge } from './severity-badge'
import { StatusIndicator } from './status-indicator'

/** The main action of an alert that is not resolved (DESIGN.md §5.1), and the inline error of the last attempt. */
export function AlertActions({ alert }: { alert: AlertRead }) {
  const { acknowledge, resolve, error } = useAlertResponse(alert)
  const reduceMotion = useReducedMotion()
  return (
    <div className="flex flex-col items-end gap-1">
      <AnimatePresence mode="wait" initial={false}>
        {alert.status !== 'resolved' && (
          <motion.div
            key={alert.status}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={reduceMotion === true ? { duration: 0 } : motionTokens.fast}
          >
            {alert.status === 'open' ? (
              <Tooltip>
                <TooltipTrigger render={<Button size="sm" onClick={acknowledge} />}>Acknowledge</TooltipTrigger>
                <TooltipContent>Tell your team you are on it</TooltipContent>
              </Tooltip>
            ) : (
              <Button size="sm" variant="secondary" onClick={resolve}>
                Resolve
              </Button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
      {error !== null && (
        <p role="alert" className="text-right text-[12px]/[16px] text-alert-red-text">
          {error}
        </p>
      )}
    </div>
  )
}

/** Props for `AlertCard`. */
export interface AlertCardProps {
  alert: AlertRead
  /** Name of the alert's team, shown on feeds that span teams (the Overview). */
  teamName?: string
}

/**
 * One alert in a feed (DESIGN.md §5.1, §9): a left bar in the rule's colour (solid when open, dashed when
 * acknowledged, faded when resolved), severity, status, last seen, occurrence counter, the rendered title linking to
 * the alert detail, body and fields, and Acknowledge or Resolve for users who may respond
 * (`can(me, 'alert.respond', alert)`).
 */
export function AlertCard({ alert, teamName }: AlertCardProps) {
  const me = useMe()
  const titleId = useId()
  // A personal rule's alert (no team) is visible to its owner, who may respond; `can` leaves that call to us.
  const mayRespond = alert.team_id === null || can(me, 'alert.respond', alert)
  const resolved = alert.status === 'resolved'

  return (
    <article
      aria-labelledby={titleId}
      className={cn(
        'relative isolate flex flex-col gap-2 overflow-hidden rounded-lg border bg-card py-3 pr-3 pl-5',
        'transition-shadow duration-(--duration-fast) ease-standard',
        resolved ? 'shadow-none' : 'shadow-card',
        alertColourClass[alert.colour],
      )}
    >
      <AlertStatusBar status={alert.status} occurrences={alert.occurrences} />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <SeverityBadge severity={alert.severity} colour={alert.colour} />
        <StatusIndicator alert={alert} meId={me.user.id} />
        {teamName !== undefined && (
          <span className="text-[12px]/[16px] font-medium text-muted-foreground">{teamName}</span>
        )}
        <div className="ml-auto flex items-center gap-3">
          <RelativeTime value={alert.last_seen_at} timeZone={me.user.timezone} />
          {alert.occurrences > 1 && <OccurrenceCounter count={alert.occurrences} />}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <h3
          id={titleId}
          className={cn(
            'text-[15px]/[22px] font-[560] transition-colors duration-(--duration-base)',
            resolved && 'text-muted-foreground',
          )}
        >
          <Link
            to="/alerts/$alertId"
            params={{ alertId: alert.id }}
            className={cn('rounded-sm hover:underline', focusRing)}
          >
            {alert.title}
          </Link>
        </h3>
        {alert.body !== null && <p className="whitespace-pre-line text-muted-foreground">{alert.body}</p>}
      </div>

      {(alert.fields.length > 0 || (mayRespond && !resolved)) && (
        <div className="flex flex-wrap items-end justify-between gap-3">
          {alert.fields.length > 0 ? (
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
          ) : (
            <span />
          )}
          {mayRespond && <AlertActions alert={alert} />}
        </div>
      )}
    </article>
  )
}
