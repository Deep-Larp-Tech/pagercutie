import type { EventSchemaRead, SourceRead } from '@/api/generated/model'
import { settlements } from './teams'

/** An event schema of Settlements with an id derived from name and version. */
export function eventSchema(name: string, version: number, overrides: Partial<EventSchemaRead> = {}): EventSchemaRead {
  return {
    id: `schema-${name}-v${version}`,
    name,
    version,
    team_id: settlements.id,
    description: null,
    json_schema: { type: 'object', properties: { workflowId: { type: 'string' } }, required: ['workflowId'] },
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

/** A webhook source of Settlements with an ingest token and an id derived from its slug. */
export function source(slug: string, name: string, overrides: Partial<SourceRead> = {}): SourceRead {
  return {
    id: `source-${slug}`,
    slug,
    name,
    type: 'webhook',
    team_id: settlements.id,
    severity: { field: null, values: {}, default: 'info' },
    enabled: true,
    ingest_url: `/ingest/${slug}`,
    has_token: true,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}
