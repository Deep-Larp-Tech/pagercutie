import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** Props for `PageHeader`. */
export interface PageHeaderProps {
  /** Page title, the page's only `h1`. */
  title: string
  /** One sentence under the title saying what the page is for. */
  description?: string
  /** Buttons for the page's actions; at most one primary (DESIGN.md §4.1). */
  actions?: ReactNode
  className?: string
}

/** Title block at the top of a page: title 24/32, optional description and actions on the right. */
export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <header className={cn('flex flex-wrap items-start justify-between gap-x-6 gap-y-3', className)}>
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-[24px]/[32px] font-semibold tracking-[-0.02em]">{title}</h1>
        {description !== undefined && <p className="text-muted-foreground">{description}</p>}
      </div>
      {actions !== undefined && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}
