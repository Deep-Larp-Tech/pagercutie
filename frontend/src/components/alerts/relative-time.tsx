import { focusRing } from '@/components/ui/styles'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useNow } from '@/hooks/use-now'
import { absoluteTime, relativeTime } from '@/lib/time'
import { cn } from '@/lib/utils'

/** How often a relative time is recomputed (ms). */
const REFRESH_MS = 30_000

/** Props for `RelativeTime`. */
export interface RelativeTimeProps {
  /** UTC ISO 8601 timestamp. */
  value: string
  /** IANA time zone for the absolute time in the tooltip; the browser's when omitted. */
  timeZone?: string
  className?: string
}

/** "3 minutes ago", with the absolute date and time in a tooltip and in `<time dateTime>`. */
export function RelativeTime({ value, timeZone, className }: RelativeTimeProps) {
  const now = useNow(REFRESH_MS)
  const absolute = absoluteTime(value, timeZone)
  return (
    <Tooltip>
      <TooltipTrigger
        render={<time dateTime={value} tabIndex={0} />}
        className={cn(
          'rounded-sm text-[12px]/[16px] font-medium text-muted-foreground tabular-nums',
          focusRing,
          className,
        )}
      >
        {relativeTime(value, now)}
      </TooltipTrigger>
      <TooltipContent>{absolute}</TooltipContent>
    </Tooltip>
  )
}
