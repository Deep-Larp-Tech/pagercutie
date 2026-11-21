import { Check, CircleX, Clock, type LucideIcon } from 'lucide-react'
import type { Channel, DeliveryStatus } from '@/api/generated/model'
import { channelLabel, channelMeans } from '@/lib/channels'
import { formatShortTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'

/** Icon and its colour for each delivery status (DESIGN.md §5.2). */
const statusIcon = {
  pending: { icon: Clock, className: 'text-muted-foreground' },
  sent: { icon: Check, className: 'text-alert-green-text' },
  failed: { icon: CircleX, className: 'text-alert-red-text' },
} as const satisfies Record<DeliveryStatus, { icon: LucideIcon; className: string }>

const attemptCount = new Intl.NumberFormat('en-GB')

/** Props for `DeliveryStatusLine`. */
export interface DeliveryStatusLineProps {
  channel: Channel
  status: DeliveryStatus
  /** Send attempts so far (`DEL-5`); shown while the delivery is failing. */
  attempts: number
  /** When the channel accepted the message (UTC ISO 8601); `null` until then. */
  sentAt: string | null
  /** IANA time zone for the sent time, normally the signed-in user's. */
  timeZone: string
  className?: string
}

/** A delivery's status as an icon and words, never colour alone (DESIGN.md §5.2, `DEL-6`). */
export function DeliveryStatusLine({ channel, status, attempts, sentAt, timeZone, className }: DeliveryStatusLineProps) {
  const { icon: Icon, className: iconClass } = statusIcon[status]
  return (
    <p className={cn('flex items-center gap-1.5 text-[12px]/[16px] text-muted-foreground', className)}>
      <Icon size={14} strokeWidth={1.75} aria-hidden className={cn('shrink-0', iconClass)} />
      <span>
        <StatusText channel={channel} status={status} attempts={attempts} sentAt={sentAt} timeZone={timeZone} />
      </span>
    </p>
  )
}

function StatusText({ channel, status, attempts, sentAt, timeZone }: Omit<DeliveryStatusLineProps, 'className'>) {
  switch (status) {
    case 'pending':
      return <>Sending {channelMeans[channel]}</>
    case 'sent':
      return sentAt === null ? (
        <>Sent {channelMeans[channel]}</>
      ) : (
        <>
          Sent {channelMeans[channel]}, <span className="font-mono tabular-nums">{formatShortTime(sentAt, timeZone)}</span>
        </>
      )
    case 'failed':
      return (
        <>
          {channelLabel[channel]} failed, retrying. {attemptCount.format(attempts)} {attempts === 1 ? 'attempt' : 'attempts'}{' '}
          so far
        </>
      )
    default:
      return status satisfies never
  }
}
