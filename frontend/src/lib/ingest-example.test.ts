import { describe, expect, test } from 'vitest'
import { absoluteIngestUrl, ingestCommand, shellQuote } from './ingest-example'

describe('absoluteIngestUrl', () => {
  test('resolves the API path against the origin and keeps an absolute URL', () => {
    expect(absoluteIngestUrl('/ingest/payments', 'https://pc.example.com')).toBe('https://pc.example.com/ingest/payments')
    expect(absoluteIngestUrl('https://in.example.com/ingest/x', 'https://pc.example.com')).toBe(
      'https://in.example.com/ingest/x',
    )
  })
})

describe('shellQuote', () => {
  test('escapes single quotes', () => {
    expect(shellQuote("it's")).toBe(`'it'\\''s'`)
  })
})

describe('ingestCommand', () => {
  const url = 'https://pc.example.com/ingest/payments'

  test('webhook: curl with the bearer token and a JSON body', () => {
    const command = ingestCommand('webhook', url, 'tok_123', 'payments')

    expect(command).toContain(`curl -X POST '${url}'`)
    expect(command).toContain(`-H 'Authorization: Bearer tok_123'`)
    expect(command).toContain(`-H 'Content-Type: application/json'`)
  })

  test('protobuf: grpcurl with the token and slug as metadata on the API origin', () => {
    expect(ingestCommand('protobuf', 'http://localhost:5173/pagercutie.v1.IngestService/Send', 'tok_123', 'ledger')).toBe(
      [
        `grpcurl -plaintext \\`,
        `  -H 'authorization: Bearer tok_123' \\`,
        `  -H 'source-slug: ledger' \\`,
        `  -d '{"payload": {"message": "Test event from grpcurl"}}' \\`,
        `  localhost:5173 pagercutie.v1.IngestService/Send`,
      ].join('\n'),
    )
  })

  test('protobuf: TLS on the default port', () => {
    const command = ingestCommand('protobuf', 'https://pc.example.com/pagercutie.v1.IngestService/Send', 't', 'ledger')

    expect(command).toMatch(/^grpcurl \\/)
    expect(command).toContain('pc.example.com:443 pagercutie.v1.IngestService/Send')
  })

  test('websocket: websocat on the ws scheme', () => {
    expect(ingestCommand('websocket', `${url}/ws`, 'tok_123', 'payments')).toBe(
      `websocat -H 'Authorization: Bearer tok_123' 'wss://pc.example.com/ingest/payments/ws'`,
    )
  })
})
