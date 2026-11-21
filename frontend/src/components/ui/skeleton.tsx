import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/** Placeholder block shaped like the content it stands for (DESIGN.md §9); no spinner. */
export function Skeleton({ className, ...props }: ComponentProps<'div'>) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn('animate-pulse rounded-md bg-muted', className)}
      {...props}
    />
  )
}
