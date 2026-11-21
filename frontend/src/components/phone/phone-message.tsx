import type { DeliveryRead } from '@/api/generated/model'
import { DeliveryStatusLine } from '@/components/delivery/delivery-status'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { focusRing } from '@/components/ui/styles'
import { channelIcon, channelLabel } from '@/lib/channels'
import { formatFullTime, formatShortTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'

/** Props for `PhoneMessage`. */
export interface PhoneMessageProps {
  delivery: DeliveryRead
  /** IANA time zone for the times shown, normally the signed-in user's. */
  timeZone: string
}

/**
 * One SMS or phone call on the simulated phone (`DEL-4`): channel, the rendered message, its delivery status, and
 * the time it was created in Geist Mono with the full date in a tooltip.
 */
export function PhoneMessage({ delivery, timeZone }: PhoneMessageProps) {
  const Icon = channelIcon[delivery.channel]
  return (
    <article className="flex flex-col gap-2 rounded-xl border bg-card p-3 text-card-foreground shadow-card">
      <header className="flex items-center gap-2">
        <span className="flex size-6 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <Icon size={14} strokeWidth={1.75} aria-hidden />
        </span>
        <h3 className="text-[12px]/[16px] font-medium">{channelLabel[delivery.channel]}</h3>
        <Tooltip>
          <TooltipTrigger
            render={<time dateTime={delivery.created_at} tabIndex={0} />}
            className={cn(
              'ml-auto rounded-sm font-mono text-[12px]/[16px] text-muted-foreground tabular-nums',
              focusRing,
            )}
          >
            {formatShortTime(delivery.created_at, timeZone)}
          </TooltipTrigger>
          <TooltipContent>{formatFullTime(delivery.created_at, timeZone)}</TooltipContent>
        </Tooltip>
      </header>
      <p className="break-words whitespace-pre-wrap">{delivery.message}</p>
      <DeliveryStatusLine
        channel={delivery.channel}
        status={delivery.status}
        attempts={delivery.attempts}
        sentAt={delivery.sent_at}
        timeZone={timeZone}
      />
    </article>
  )
}
