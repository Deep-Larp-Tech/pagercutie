import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

/** Data table: rows divided by `--border`, no card (DESIGN.md §7); scrolls sideways inside its box on narrow screens. */
export function Table({ className, ...props }: ComponentProps<'table'>) {
  return (
    <div data-slot="table-container" className="relative w-full overflow-x-auto">
      <table data-slot="table" className={cn('w-full caption-bottom text-sm', className)} {...props} />
    </div>
  )
}

/** Header row group. */
export function TableHeader({ className, ...props }: ComponentProps<'thead'>) {
  return <thead data-slot="table-header" className={cn('[&_tr]:border-b', className)} {...props} />
}

/** Body row group. */
export function TableBody({ className, ...props }: ComponentProps<'tbody'>) {
  return <tbody data-slot="table-body" className={cn('[&_tr:last-child]:border-0', className)} {...props} />
}

/** One row. */
export function TableRow({ className, ...props }: ComponentProps<'tr'>) {
  return <tr data-slot="table-row" className={cn('border-b', className)} {...props} />
}

/** Column heading in metadata type (12 / 16, muted). */
export function TableHead({ className, ...props }: ComponentProps<'th'>) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        'h-9 px-3 text-left align-middle text-[12px]/[16px] font-medium whitespace-nowrap text-muted-foreground first:pl-0 last:pr-0',
        className,
      )}
      {...props}
    />
  )
}

/** One cell. */
export function TableCell({ className, ...props }: ComponentProps<'td'>) {
  return <td data-slot="table-cell" className={cn('h-12 px-3 align-middle first:pl-0 last:pr-0', className)} {...props} />
}
