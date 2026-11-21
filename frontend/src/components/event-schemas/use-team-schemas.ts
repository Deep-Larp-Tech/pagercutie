import { useQuery } from '@tanstack/react-query'
import { getListEventSchemasQueryOptions, type listEventSchemasResponse } from '@/api/generated/event-schemas/event-schemas'
import type { EventSchemaRead } from '@/api/generated/model'
import { unexpectedStatusMessage } from '@/lib/api'
import { OFFLINE, PAGE_LIMIT } from '@/lib/pagination'

/** The team's event schemas as a picker or a lookup needs them. */
export type TeamSchemas =
  | { kind: 'loading' }
  | { kind: 'failed'; message: string }
  /** Sorted by name, newest version first. */
  | { kind: 'listed'; schemas: EventSchemaRead[]; byId: ReadonlyMap<string, EventSchemaRead> }

/** Name and version as people refer to a schema, e.g. `payment-failed v2`. */
export function schemaLabel(schema: Pick<EventSchemaRead, 'name' | 'version'>): string {
  return `${schema.name} v${schema.version}`
}

/** Sorts schemas by name, newest version first. */
export function bySchemaName(a: EventSchemaRead, b: EventSchemaRead): number {
  return a.name.localeCompare(b.name) || b.version - a.version
}

/** Every version of one schema name, newest first. */
export interface SchemaGroup {
  name: string
  /** At least one; `versions[0]` is the latest. */
  versions: [EventSchemaRead, ...EventSchemaRead[]]
}

/** Groups schemas by name, names in alphabetical order and versions newest first. */
export function groupByName(schemas: readonly EventSchemaRead[]): SchemaGroup[] {
  const groups = new Map<string, SchemaGroup>()
  for (const schema of [...schemas].sort(bySchemaName)) {
    const group = groups.get(schema.name)
    if (group === undefined) groups.set(schema.name, { name: schema.name, versions: [schema] })
    else group.versions.push(schema)
  }
  return [...groups.values()]
}

function readSchemas(response: listEventSchemasResponse): TeamSchemas {
  switch (response.status) {
    case 200: {
      const schemas = [...response.data].sort(bySchemaName)
      return { kind: 'listed', schemas, byId: new Map(schemas.map((schema) => [schema.id, schema])) }
    }
    case 401:
      return { kind: 'loading' }
    case 422:
      return { kind: 'failed', message: "Couldn't load the event schemas. Reload the page and try again." }
    default:
      return { kind: 'failed', message: unexpectedStatusMessage(response) }
  }
}

/**
 * The first `PAGE_LIMIT` event schemas of a team (`GET /event-schemas?team_id=`), for the source form's schema
 * pickers and the source list's schema names.
 */
export function useTeamSchemas(teamId: string): TeamSchemas {
  const query = useQuery(getListEventSchemasQueryOptions({ team_id: teamId, limit: PAGE_LIMIT }))
  if (query.isPending) return { kind: 'loading' }
  if (query.isError) return { kind: 'failed', message: OFFLINE }
  return readSchemas(query.data)
}
