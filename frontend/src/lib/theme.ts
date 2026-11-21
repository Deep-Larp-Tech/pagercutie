import type { ResolvedTheme } from '@/hooks/use-resolved-theme'

/** The user's theme choice (DESIGN.md §3); `system` follows `prefers-color-scheme`. */
export type ThemeChoice = 'light' | 'dark' | 'system'

/** `localStorage` key the choice is stored under; `index.html` reads the same key before first paint. */
export const THEME_KEY = 'theme'

/** Choices in the order the toggle shows them. */
export const themeChoices = ['light', 'dark', 'system'] as const satisfies readonly ThemeChoice[]

/** Media query for the OS dark theme. */
export const darkSchemeQuery = '(prefers-color-scheme: dark)'

function isThemeChoice(value: string | null): value is ThemeChoice {
  return value === 'light' || value === 'dark' || value === 'system'
}

/** A choice made while storage was unavailable; it lasts for this page only. */
let unstoredChoice: ThemeChoice | null = null

/** Called after every `storeThemeChoice`, so each control showing the choice re-reads it. */
const listeners = new Set<() => void>()

/** Calls `listener` after every choice change; returns the unsubscribe function (for `useSyncExternalStore`). */
export function subscribeThemeChoice(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** The stored choice, or `system` when nothing valid is stored or storage is unavailable. */
export function readThemeChoice(): ThemeChoice {
  if (unstoredChoice !== null) return unstoredChoice
  try {
    const stored = localStorage.getItem(THEME_KEY)
    return isThemeChoice(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

/** Stores the choice; storage can be unavailable (private mode), and the choice then lasts for this page only. */
export function storeThemeChoice(choice: ThemeChoice): void {
  try {
    localStorage.setItem(THEME_KEY, choice)
    unstoredChoice = null
  } catch {
    unstoredChoice = choice
  }
  for (const listener of listeners) listener()
}

function resolveTheme(choice: ThemeChoice): ResolvedTheme {
  if (choice !== 'system') return choice
  return matchMedia(darkSchemeQuery).matches ? 'dark' : 'light'
}

/**
 * Sets `data-theme` and `color-scheme` on `<html>` for the choice, inside a View Transition cross-fade (250 ms, set
 * in `index.css`); switches at once when View Transitions are unsupported or reduced motion is on.
 */
export function applyTheme(choice: ThemeChoice): void {
  const theme = resolveTheme(choice)
  const root = document.documentElement
  if (root.dataset.theme === theme) return
  const update = () => {
    root.dataset.theme = theme
    root.style.colorScheme = theme
  }
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches
  if (typeof document.startViewTransition === 'function' && !reducedMotion) {
    document.startViewTransition(update)
  } else {
    update()
  }
}
