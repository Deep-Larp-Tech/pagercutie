import type { SourceType } from '@/api/generated/model'

/** Label of each source type in the UI (`ING-1`). */
export const sourceTypeLabel = {
  webhook: 'Webhook',
  websocket: 'WebSocket',
  protobuf: 'gRPC (protobuf)',
} as const satisfies Record<SourceType, string>

/** One line on how producers of each source type send events. */
export const sourceTypeHelp = {
  webhook: 'Producers POST one JSON event per request.',
  websocket: 'Producers keep a WebSocket open and send one JSON event per message.',
  protobuf: 'Producers call IngestService.Send over gRPC with a protobuf Struct payload; PagerCutie decodes it to JSON.',
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

/** `host:port` of a URL for grpcurl, which needs the port even when it is the scheme's default. */
function grpcTarget(url: URL): string {
  return `${url.hostname}:${url.port || (url.protocol === 'https:' ? '443' : '80')}`
}

const commandFor = {
  webhook: (url, token) =>
    [
      `curl -X POST ${shellQuote(url)} \\`,
      `  -H ${shellQuote(`Authorization: Bearer ${token}`)} \\`,
      `  -H 'Content-Type: application/json' \\`,
      `  -d '{"message": "Test event from curl"}'`,
    ].join('\n'),
  // The URL is the gRPC method path on the API origin; the source goes in `source-slug` metadata (ADR-0097).
  protobuf: (url, token, slug) => {
    const parsed = new URL(url)
    return [
      `grpcurl${parsed.protocol === 'https:' ? '' : ' -plaintext'} \\`,
      `  -H ${shellQuote(`authorization: Bearer ${token}`)} \\`,
      `  -H ${shellQuote(`source-slug: ${slug}`)} \\`,
      `  -d '{"payload": {"message": "Test event from grpcurl"}}' \\`,
      `  ${grpcTarget(parsed)} ${parsed.pathname.slice(1)}`,
    ].join('\n')
  },
  websocket: (url, token) =>
    `websocat -H ${shellQuote(`Authorization: Bearer ${token}`)} ${shellQuote(url.replace(/^http/, 'ws'))}`,
} as const satisfies Record<SourceType, (url: string, token: string, slug: string) => string>

/** A command that sends one test event to a source, ready to paste into a terminal (`NFR-4`). */
export function ingestCommand(type: SourceType, url: string, token: string, slug: string): string {
  return commandFor[type](url, token, slug)
}
