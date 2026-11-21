import type { Transition } from 'motion/react'

const standard = [0.2, 0.8, 0.2, 1] as const

/** Motion tokens from DESIGN.md §8 as motion/react transitions; the CSS side lives in `index.css`. */
export const motionTokens = {
  /** 150 ms: hover, press, colour changes. */
  fast: { duration: 0.15, ease: standard },
  /** 250 ms: popovers, tabs, page and theme changes. */
  base: { duration: 0.25, ease: standard },
  /** Feed enter and reorder, counter bump, the sliding nav highlight. */
  spring: { type: 'spring', stiffness: 380, damping: 32 },
  /** 200 ms: anything leaving. */
  exit: { duration: 0.2, ease: [0.4, 0, 1, 1] },
} as const satisfies Record<string, Transition>

/** Enter animation for a screen whose path changed: fades in and rises 6 px. No exit, so the old screen never renders the new route. */
export const screenEnter = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  transition: motionTokens.base,
} as const

/** How long a resolved alert stays in a feed that filters it out, so the user sees the result first (ms). */
export const RESOLVE_EXIT_MS = 700

/** Length of the card tint flash on a repeat occurrence (ms). */
export const FLASH_MS = 900
