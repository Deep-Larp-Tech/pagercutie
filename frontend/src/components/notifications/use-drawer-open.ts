import { useCallback, useState } from 'react'

/** `localStorage` key remembering whether the notifications drawer was open (convenience only). */
export const DRAWER_OPEN_KEY = 'notifications-drawer'

function readStored(): boolean {
  try {
    return localStorage.getItem(DRAWER_OPEN_KEY) === 'open'
  } catch {
    return false
  }
}

/** Whether the notifications drawer is open, remembered across reloads in this browser. */
export function useDrawerOpen() {
  const [open, setOpenState] = useState(readStored)
  const setOpen = useCallback((next: boolean) => {
    setOpenState(next)
    try {
      if (next) localStorage.setItem(DRAWER_OPEN_KEY, 'open')
      else localStorage.removeItem(DRAWER_OPEN_KEY)
    } catch {
    }
  }, [])
  return [open, setOpen] as const
}
