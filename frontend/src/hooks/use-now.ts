import { useEffect, useState } from 'react'

/** The current time in ms, updated every `intervalMs`; relative times use it to stay current. */
export function useNow(intervalMs: number): number {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])
  return now
}
