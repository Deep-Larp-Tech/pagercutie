import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/** Props for `Section`. */
export interface SectionProps {
  /** Section title, an `h2` under the page's `h1`. */
  title: string
  /** One line under the title. */
  description?: string
  children: ReactNode
  className?: string
}

/** A titled block of a settings page, separated from the next by spacing (DESIGN.md §7). */
export function Section({ title, description, children, className }: SectionProps) {
  return (
    <section className={cn('flex flex-col gap-4', className)}>
      <div className="flex flex-col gap-1">
        <h2 className="text-[18px]/[26px] font-semibold tracking-[-0.01em]">{title}</h2>
        {description !== undefined && <p className="text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  )
}

/** Loading stand-in for a settings section: `rows` bars the height of a form row. */
export function SectionSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3" data-testid="section-skeleton">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-8 w-full max-w-[480px]" />
      ))}
    </div>
  )
}

/** Props for `SectionError`. */
export interface SectionErrorProps {
  /** What went wrong and what to do, per DESIGN.md §10. */
  message: string
  /** Loads the section again; omitted when retrying cannot help. */
  onRetry?: () => void
}

/** A section that could not load: the message, announced, and a **Try again** button. */
export function SectionError({ message, onRetry }: SectionErrorProps) {
  return (
    <div className="flex flex-col items-start gap-3">
      <p role="alert" className="text-muted-foreground">
        {message}
      </p>
      {onRetry !== undefined && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

/** A form-level error under the fields, in alert red; render it only while there is one. */
export function FormError({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
      {children}
    </p>
  )
}
