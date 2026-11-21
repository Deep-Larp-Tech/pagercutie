import type { ErrorRead, HTTPValidationError } from '@/api/generated/model'
import { unexpectedStatusMessage } from '@/lib/api'

/** A generated list response whose contract documents `200`, `401` and `422` (`GET /alerts`, `/rules`, `/runbooks`). */
export type ListResponse<T> = (
  | { status: 200; data: T[] }
  | { status: 401; data: ErrorRead }
  | { status: 422; data: HTTPValidationError }
) & { headers: Headers }

/** What one group of the command menu can show for its list. */
export type GroupState<T> =
  | { kind: 'loading' }
  /** The list answered with an error; the group shows `message` as one muted line. */
  | { kind: 'failed'; message: string }
  /** A `401`: the sign-in redirect is under way, so the group shows nothing. */
  | { kind: 'silent' }
  | { kind: 'listed'; items: T[] }

/**
 * Reads one list response for a command menu group. An undocumented status (the `501` stub) becomes the shared
 * fallback line, so the group says "This feature isn't available yet." instead of failing the menu (ADR-0049).
 */
export function groupState<T>(response: ListResponse<T> | undefined, networkError: boolean): GroupState<T> {
  if (response === undefined) {
    return networkError
      ? { kind: 'failed', message: "Couldn't reach PagerCutie. Check your connection." }
      : { kind: 'loading' }
  }
  switch (response.status) {
    case 200:
      return { kind: 'listed', items: response.data }
    case 401:
      return { kind: 'silent' }
    case 422:
      return { kind: 'failed', message: "Couldn't search this list. Reload the page and try again." }
    default:
      return { kind: 'failed', message: unexpectedStatusMessage(response) }
  }
}

/** Whether every word of `search` appears in one of `texts`, ignoring case; an empty search matches everything. */
export function matches(search: string, ...texts: readonly (string | null | undefined)[]): boolean {
  const haystack = texts.filter((text) => text != null).join(' ').toLowerCase()
  return search
    .toLowerCase()
    .split(/\s+/)
    .filter((word) => word !== '')
    .every((word) => haystack.includes(word))
}

/** Whether the browser runs on an Apple platform, where the shortcut is ⌘K instead of Ctrl K. */
export function isApplePlatform(): boolean {
  return /Mac|iPhone|iPad|iPod/.test(navigator.platform)
}
