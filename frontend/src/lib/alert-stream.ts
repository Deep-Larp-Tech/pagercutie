import type { AlertEvent } from '@/api/generated/model'
import { parseAlertEvent } from './alert-feed'

/** How long a connection must stay open before the reconnect delay starts again from 1 s (ms). */
export const STABLE_AFTER_MS = 5_000

/** Delay before reconnect attempt `attempt` (0-based): 1 s doubling up to 30 s (ms). */
export function reconnectDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 30_000)
}

/** Callbacks of `openAlertStream`. */
export interface AlertStreamHandlers {
  /** The server accepted a connection, the first or a reopened one. */
  onOpen: () => void
  /** One valid `AlertEvent`; invalid messages are dropped. */
  onEvent: (event: AlertEvent) => void
  /** The connection dropped or was refused; it is reopened after `reconnectDelay`. */
  onDrop: () => void
}

/** A connection opened by `openAlertStream`. */
export interface AlertStreamConnection {
  /** Closes the connection and cancels a pending reopen. */
  close: () => void
  /** Closes the connection and opens a new one now, with the delay back at 1 s. */
  reconnect: () => void
}

/**
 * `EventSource(url)` on `GET /alerts/stream`, reopened after every drop with backoff (ADR-0054): 1 s doubling to 30 s,
 * back to 1 s once a connection stays open for `STABLE_AFTER_MS`.
 */
export function openAlertStream(url: string, handlers: AlertStreamHandlers): AlertStreamConnection {
  let source: EventSource | undefined
  let attempt = 0
  let retryTimer: ReturnType<typeof setTimeout> | undefined
  let stableTimer: ReturnType<typeof setTimeout> | undefined

  const connect = () => {
    const current = new EventSource(url)
    source = current
    current.onopen = () => {
      stableTimer = setTimeout(() => {
        attempt = 0
      }, STABLE_AFTER_MS)
      handlers.onOpen()
    }
    current.onmessage = (message) => {
      const payload: unknown = message.data
      if (typeof payload !== 'string') return
      const event = parseAlertEvent(payload)
      if (event !== null) handlers.onEvent(event)
    }
    current.onerror = () => {
      current.close()
      clearTimeout(stableTimer)
      handlers.onDrop()
      retryTimer = setTimeout(connect, reconnectDelay(attempt))
      attempt += 1
    }
  }

  const close = () => {
    source?.close()
    clearTimeout(retryTimer)
    clearTimeout(stableTimer)
  }

  connect()
  return {
    close,
    reconnect: () => {
      close()
      attempt = 0
      connect()
    },
  }
}
