import type { SourceType } from '@/api/generated/model'

/** Label of each source type in the UI (`ING-1`). */
export const sourceTypeLabel = {
  webhook: 'Webhook',
  websocket: 'WebSocket',
  protobuf: 'Protobuf over HTTP',
} as const satisfies Record<SourceType, string>

/** One line on how producers of each source type send events. */
export const sourceTypeHelp = {
  webhook: 'Producers POST one JSON event per request.',
  websocket: 'Producers keep a WebSocket open and send one JSON event per message.',
  protobuf: 'Producers POST protobuf messages; PagerCutie decodes them to JSON.',
} as const satisfies Record<SourceType, string>

/**
 * Absolute ingest URL for a source's `ingest_url`, which the API returns as a path (`/ingest/payments-webhook`).
 * An absolute `ingestUrl` is kept as it is.
 */
export function absoluteIngestUrl(ingestUrl: string, origin: string): string {
  return new URL(ingestUrl, origin).toString()
}

/** `value` in single quotes for a POSIX shell. */
export function shellQuote(value: string): string {
  return `'${value.replaceAll("'", `'\\''`)}'`
}

const commandFor = {
  webhook: (url, token) =>
    [
      `curl -X POST ${shellQuote(url)} \\`,
      `  -H ${shellQuote(`Authorization: Bearer ${token}`)} \\`,
      `  -H 'Content-Type: application/json' \\`,
      `  -d '{"message": "Test event from curl"}'`,
    ].join('\n'),
  protobuf: (url, token) =>
    [
      `curl -X POST ${shellQuote(url)} \\`,
      `  -H ${shellQuote(`Authorization: Bearer ${token}`)} \\`,
      `  -H 'Content-Type: application/x-protobuf' \\`,
      `  --data-binary @event.bin`,
    ].join('\n'),
  websocket: (url, token) =>
    `websocat -H ${shellQuote(`Authorization: Bearer ${token}`)} ${shellQuote(url.replace(/^http/, 'ws'))}`,
} as const satisfies Record<SourceType, (url: string, token: string) => string>

/** A command that sends one test event to a source, ready to paste into a terminal (`NFR-4`). */
export function ingestCommand(type: SourceType, url: string, token: string): string {
  return commandFor[type](url, token)
}
