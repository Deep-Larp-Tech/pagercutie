import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Props for `EmptyState`. */
export interface EmptyStateProps {
  /** Icon drawn above the title at 20 px. */
  icon: LucideIcon
  /** What is missing, as a sentence. */
  title: string
  /** One line saying why, or what fills this space. */
  description: string
  /** One button or link that resolves the empty state. */
  action?: ReactNode
  /** `role="alert"` for error pages, so screen readers announce them. */
  role?: 'alert'
  className?: string
}

/** Stand-in for content that is not there: an icon, a title, one line and an optional action, centred. */
export function EmptyState({ icon: Icon, title, description, action, role, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-3 rounded-lg border border-dashed px-6 py-12 text-center',
        className,
      )}
    >
      <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Icon size={20} strokeWidth={1.75} aria-hidden />
      </span>
      <div role={role} className="flex max-w-[420px] flex-col gap-1">
        <h2 className="text-[15px]/[22px] font-[560]">{title}</h2>
        <p className="text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  )
}
