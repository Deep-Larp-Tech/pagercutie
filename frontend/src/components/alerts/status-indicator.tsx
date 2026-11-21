import { Check } from 'lucide-react'
import type { AlertRead } from '@/api/generated/model'
import { cn } from '@/lib/utils'

/** Props for `StatusIndicator`. */
export interface StatusIndicatorProps {
  alert: Pick<AlertRead, 'status' | 'severity' | 'resolution' | 'acknowledged_by'>
  /** The signed-in user's id, to say "You're on it" for their own acknowledgement. */
  meId: string
  className?: string
}

const label = 'flex items-center gap-1.5 text-[12px]/[16px] font-medium'

/**
 * Alert status by shape and words, in the colour of the nearest `alert-<colour>` (DESIGN.md §5.1): a filled dot
 * when open (pinging when critical), a hollow ring when acknowledged, a check when resolved.
 */
export function StatusIndicator({ alert, meId, className }: StatusIndicatorProps) {
  switch (alert.status) {
    case 'open':
      return (
        <span className={cn(label, 'text-c-text', className)}>
          <span className="relative flex size-2.5" aria-hidden>
            {alert.severity === 'critical' && (
              <span className="absolute inline-flex size-full animate-live-ping rounded-full bg-c opacity-75" />
            )}
            <span className="relative inline-flex size-2.5 rounded-full bg-c" />
          </span>
          Open
        </span>
      )
    case 'acknowledged':
      return (
        <span className={cn(label, 'text-foreground', className)}>
          <span className="size-2.5 rounded-full border-2 border-c" aria-hidden />
          {alert.acknowledged_by === meId ? "You're on it" : 'Someone is on it'}
        </span>
      )
    case 'resolved':
      return (
        <span className={cn(label, 'text-muted-foreground', className)}>
          <Check size={14} strokeWidth={1.75} aria-hidden />
          {alert.resolution === 'auto' ? 'Resolved automatically' : 'Resolved'}
        </span>
      )
    default:
      return alert.status satisfies never
  }
}
