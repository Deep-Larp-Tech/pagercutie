import { useState } from 'react'

/** How many times `value` has gone up since mount; a change of this number keys a one-off "it happened again" animation. */
export function useIncrease(value: number): number {
  const [previous, setPrevious] = useState(value)
  const [increases, setIncreases] = useState(0)
  if (value !== previous) {
    setPrevious(value)
    if (value > previous) setIncreases(increases + 1)
  }
  return increases
}
