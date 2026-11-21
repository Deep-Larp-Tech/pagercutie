import { useRef, type ReactNode } from 'react'
import { useBlocker } from '@tanstack/react-router'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

/** What `useUnsavedChanges` returns. */
export interface UnsavedChanges {
  /** Lets the next navigation through without asking, e.g. right after a save or a delete. */
  allowNextNavigation: () => void
  /** The "Leave without saving?" dialog; render it once on the page. */
  dialog: ReactNode
}

/**
 * Asks before leaving a page with unsaved changes: in-app navigation shows a dialog, closing or reloading the tab
 * shows the browser's own prompt.
 */
export function useUnsavedChanges(dirty: boolean): UnsavedChanges {
  const allowed = useRef(false)
  const blocker = useBlocker({
    shouldBlockFn: () => {
      if (allowed.current) {
        allowed.current = false
        return false
      }
      return dirty
    },
    enableBeforeUnload: () => dirty && !allowed.current,
    withResolver: true,
  })
  return {
    allowNextNavigation: () => {
      allowed.current = true
    },
    dialog: (
      <ConfirmDialog
        open={blocker.status === 'blocked'}
        onOpenChange={(open) => !open && blocker.reset?.()}
        title="Leave without saving?"
        description="Your changes on this page are lost."
        confirmLabel="Discard changes"
        pendingLabel="Leaving…"
        pending={false}
        error={null}
        onConfirm={() => blocker.proceed?.()}
      />
    ),
  }
}
