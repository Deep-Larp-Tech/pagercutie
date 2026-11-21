import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

/** Service worker serving the generated handlers in the browser; started from `main.tsx` when `VITE_MOCK=1`. */
export const worker = setupWorker(...handlers)
