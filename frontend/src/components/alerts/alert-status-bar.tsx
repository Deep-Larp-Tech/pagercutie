import { motion, useReducedMotion } from 'motion/react'
import type { AlertStatus } from '@/api/generated/model'
import { useIncrease } from '@/hooks/use-increase'
import { FLASH_MS } from '@/lib/motion'
import { cn } from '@/lib/utils'

/** Props for `AlertStatusBar`. */
export interface AlertStatusBarProps {
  status: AlertStatus
  /** Events folded into the alert; each increase flashes the tint once. */
  occurrences: number
}

/**
 * The left bar of an alert in the nearest `alert-<colour>` (DESIGN.md §5.1): solid when open, dashed when acknowledged,
 * faded when resolved; plus the one-off tint flash on a repeat occurrence (§8). Its parent is `relative isolate`.
 */
export function AlertStatusBar({ status, occurrences }: AlertStatusBarProps) {
  const reduceMotion = useReducedMotion()
  const repeats = useIncrease(occurrences)
  const resolved = status === 'resolved'
  const acknowledged = status === 'acknowledged'
  return (
    <>
      <span
        aria-hidden
        className={cn(
          'absolute inset-y-0 left-0 w-1 bg-c transition-opacity duration-(--duration-base) ease-standard',
          acknowledged ? 'opacity-0' : resolved ? 'opacity-35' : 'opacity-100',
        )}
      />
      <span
        aria-hidden
        className={cn(
          'absolute inset-y-0 left-0 w-1 bg-[repeating-linear-gradient(to_bottom,var(--c)_0_6px,transparent_6px_10px)]',
          'transition-opacity duration-(--duration-base) ease-standard',
          acknowledged ? 'opacity-100' : 'opacity-0',
        )}
      />
      {repeats > 0 && reduceMotion !== true && (
        <motion.span
          key={repeats}
          aria-hidden
          data-testid="repeat-flash"
          className="pointer-events-none absolute inset-0 -z-10 bg-c-tint"
          initial={{ opacity: 1 }}
          animate={{ opacity: 0 }}
          transition={{ duration: FLASH_MS / 1000, ease: 'easeOut' }}
        />
      )}
    </>
  )
}
