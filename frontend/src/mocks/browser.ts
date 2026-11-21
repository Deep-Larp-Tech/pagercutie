import { http, passthrough } from 'msw'
import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

/**
 * Lets Vite's module requests through before any API handler sees them: the generated `*\/users/:userId` pattern
 * also matches the module `/src/api/generated/users/users.ts`, which would load as JSON and break the page.
 */
const viteModules = http.get(`${location.origin}/src/*`, () => passthrough())

/** Service worker serving the generated handlers in the browser; started from `main.tsx` when `VITE_MOCK=1`. */
export const worker = setupWorker(viteModules, ...handlers)
