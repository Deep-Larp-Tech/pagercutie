import type { AlertEvent } from '@/api/generated/model'

/**
 * Stand-in for the browser's `EventSource`, which jsdom lacks; `setup.ts` installs it before every test. Tests drive
 * the latest connection with `open()`, `send()` and `fail()` inside `act()`.
 */
export class FakeEventSource {
  /** Every connection opened since the test started, oldest first. */
  static instances: FakeEventSource[] = []

  /** The most recent connection; throws when none was opened. */
  static latest(): FakeEventSource {
    const source = FakeEventSource.instances.at(-1)
    if (source === undefined) throw new Error('No EventSource was opened')
    return source
  }

  readonly url: string
  closed = false
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(url: string | URL) {
    this.url = String(url)
    FakeEventSource.instances.push(this)
  }

  close(): void {
    this.closed = true
  }

  /** The server accepted the connection. */
  open(): void {
    this.onopen?.(new Event('open'))
  }

  /** The server sent one message with `event` as JSON, or `raw` text as is. */
  send(event: AlertEvent | { raw: string }): void {
    const data = 'raw' in event ? event.raw : JSON.stringify(event)
    this.onmessage?.(new MessageEvent('message', { data }))
  }

  /** The connection dropped or was refused. */
  fail(): void {
    this.onerror?.(new Event('error'))
  }
}
