import type { Transition } from 'motion/react'

/** `spring` token (DESIGN.md §8): feed enter, reorder, counter bump. */
export const spring = { type: 'spring', stiffness: 380, damping: 32 } as const satisfies Transition

/** `exit` token: 200 ms, for anything leaving. */
export const exit = { duration: 0.2, ease: [0.4, 0, 1, 1] } as const satisfies Transition

/** The plain fade that replaces movement under reduced motion: 150 ms (`fast`). */
export const fade = { duration: 0.15, ease: [0.2, 0.8, 0.2, 1] } as const satisfies Transition

/** How long a resolved alert stays in a feed that filters it out, so the user sees the result first (ms). */
export const RESOLVE_EXIT_MS = 700

/** Length of the card tint flash on a repeat occurrence (ms). */
export const FLASH_MS = 900
