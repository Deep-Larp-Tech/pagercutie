import type { EventSchemaRead } from '@/api/generated/model'

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
