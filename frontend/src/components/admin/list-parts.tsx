import type { ReactNode } from 'react'
import { MoreHorizontal, Pencil, Trash2, TriangleAlert } from 'lucide-react'
import { EmptyState } from '@/components/shell/empty-state'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { TableCell, TableRow } from '@/components/ui/table'
import type { OffsetPages } from '@/lib/pagination'

/** Rows of grey bars standing in for a table while its first page loads; one bar per column. */
export function SkeletonRows({ columns, rows = 5 }: { columns: number; rows?: number }) {
  return Array.from({ length: rows }, (_, row) => (
    <TableRow key={row} data-testid="skeleton-row">
      {Array.from({ length: columns }, (_, column) => (
        <TableCell key={column}>
          <Skeleton className="h-4 w-full max-w-40" />
        </TableCell>
      ))}
    </TableRow>
  ))
}

/** Error state for a list whose first page failed, with **Try again**. */
export function ListFailed({ title, message, onRetry }: { title: string; message: string; onRetry: () => void }) {
  return (
    <EmptyState
      icon={TriangleAlert}
      role="alert"
      title={title}
      description={message}
      action={
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      }
    />
  )
}

/** **Show more** under a list whose last page was full, and the error of the last attempt. */
export function ShowMore<T>({ pages }: { pages: OffsetPages<T> }) {
  const moreError = pages.list.kind === 'listed' ? pages.list.moreError : null
  if (!pages.hasMore && moreError === null) return null
  return (
    <div className="flex flex-col items-center gap-2">
      {moreError !== null && (
        <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
          {moreError}
        </p>
      )}
      <Button
        variant="secondary"
        disabled={pages.loadingMore}
        onClick={pages.hasMore ? pages.loadMore : pages.retry}
      >
        {pages.loadingMore ? 'Loading…' : pages.hasMore ? 'Show more' : 'Try again'}
      </Button>
    </div>
  )
}

/** Props for `RowActions`. */
export interface RowActionsProps {
  /** Name of the row's user or team, for the menu's accessible label. */
  name: string
  onEdit: () => void
  /** Omitted when the row cannot be deleted (the signed-in admin's own row). */
  onDelete?: () => void
  /** Labels of the two items, e.g. "Edit user" and "Delete user". */
  editLabel: string
  deleteLabel: string
}

/** Menu at the end of a row with **Edit** and, when allowed, **Delete**. */
export function RowActions({ name, onEdit, onDelete, editLabel, deleteLabel }: RowActionsProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${name}`} />}>
        <MoreHorizontal strokeWidth={1.75} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={onEdit}>
          <Pencil strokeWidth={1.75} />
          {editLabel}
        </DropdownMenuItem>
        {onDelete !== undefined && (
          <DropdownMenuItem variant="destructive" onClick={onDelete}>
            <Trash2 strokeWidth={1.75} />
            {deleteLabel}
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** Error line at the bottom of a form, for problems no single field owns. */
export function FormError({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
      {children}
    </p>
  )
}
