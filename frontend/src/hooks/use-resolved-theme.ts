import { useSyncExternalStore } from 'react'

/** Theme currently applied to `<html data-theme>` (DESIGN.md §3). */
export type ResolvedTheme = 'light' | 'dark'

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  return () => observer.disconnect()
}

function read(): ResolvedTheme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

/** Follows `data-theme` on `<html>`, which the pre-paint script and the theme toggle set. */
export function useResolvedTheme(): ResolvedTheme {
  return useSyncExternalStore(subscribe, read)
}
