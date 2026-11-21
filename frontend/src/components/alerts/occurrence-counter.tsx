import { motion, useReducedMotion } from 'motion/react'
import { useIncrease } from '@/hooks/use-increase'
import { motionTokens } from '@/lib/motion'
import { cn } from '@/lib/utils'

/** Props for `OccurrenceCounter`. */
export interface OccurrenceCounterProps {
  /** Events folded into the alert (`NOI-1`). */
  count: number
  className?: string
}

/** `×12` in Geist Mono; scales to 1.2 and back when the count goes up (DESIGN.md §8). */
export function OccurrenceCounter({ count, className }: OccurrenceCounterProps) {
  const bumps = useIncrease(count)
  const reduceMotion = useReducedMotion()
  return (
    <motion.span
      key={bumps}
      initial={bumps === 0 || reduceMotion === true ? false : { scale: 1.2 }}
      animate={{ scale: 1 }}
      transition={motionTokens.spring}
      aria-label={`${count.toLocaleString('en')} occurrences`}
      className={cn(
        'inline-block font-mono text-[13px]/[20px] font-[450] text-muted-foreground tabular-nums',
        className,
      )}
    >
      ×{count.toLocaleString('en')}
    </motion.span>
  )
}
