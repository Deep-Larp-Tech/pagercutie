import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, vi } from 'vitest'
import { FakeEventSource } from './event-source'
import { server } from './server'

// Whole-app renders can take over the 1 s default when the machine is busy; `findBy` still returns on first match.
configure({ asyncUtilTimeout: 3_000 })

// jsdom has no scrollTo; the router calls it after every navigation.
window.scrollTo = () => {}

// jsdom has no matchMedia; the theme toggle reads it. Every query answers "no match" (light, motion allowed).
window.matchMedia = (query: string): MediaQueryList => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
})

// jsdom has no EventSource; the live feed opens one on every feed screen.
beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
})

// A request without a handler fails the test, so no test can reach an endpoint it did not declare.
beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
})
afterAll(() => server.close())
