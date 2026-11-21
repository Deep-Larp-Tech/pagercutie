import { setupServer } from 'msw/node'

/** MSW server for tests; starts with no handlers, so each test declares the endpoints it calls. */
export const server = setupServer()
