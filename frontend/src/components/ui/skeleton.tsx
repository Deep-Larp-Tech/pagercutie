import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/**
 * Placeholder block shaped like the content it stands for (DESIGN.md §9); no spinner. Invisible for its first 200 ms
 * so data that answers fast replaces it without a flash.
 */
export function Skeleton({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn('animate-skeleton rounded-md bg-muted', className)}
      {...props}
    />
  )
}
