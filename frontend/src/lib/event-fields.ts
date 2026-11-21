import { Severity, type Scalar } from '@/api/generated/model'
import { LEAF_OPS, type LeafOp, type ValueType } from './rule-condition'

/** What kind of value a field holds, as far as the event schemas say. */
export type FieldType = 'string' | 'number' | 'boolean' | 'array' | 'object' | 'severity' | 'unknown'

/** A field path a rule can test or show, with what the schemas say about it. */
export interface EventField {
  /** Dot path into the normalised event, e.g. `payload.error.code` (SPEC §4.3). */
  path: string
  type: FieldType
  /** Allowed values (`enum`), offered as suggestions. */
  values: readonly Scalar[]
  /** The schema's `description`, if any. */
  description: string | null
}

/** Fields every event has besides its payload (SPEC §4.2); `severity` is ordered (SPEC §8.1). */
export const METADATA_FIELDS: readonly EventField[] = [
  { path: 'source', type: 'string', values: [], description: 'Slug of the source that received the event' },
  { path: 'severity', type: 'severity', values: Object.values(Severity), description: 'Normalised severity, ordered' },
  { path: 'schema_id', type: 'string', values: [], description: 'Id of the event schema' },
]

/** Nesting depth the walk stops at, so a recursive `$ref` cannot loop. */
const MAX_DEPTH = 8

type JsonObject = { [key: string]: unknown }

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** `value` when it is an array, typed as `unknown[]` rather than the `any[]` `Array.isArray` narrows to. */
function arrayOf(value: unknown): readonly unknown[] | null {
  return Array.isArray(value) ? value : null
}

function isScalar(value: unknown): value is Scalar {
  return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

/** The sub-schema a local `$ref` (`#/$defs/Error`, `#/definitions/Error`) points at. */
function resolveRef(root: JsonObject, schema: JsonObject): JsonObject {
  const ref = schema.$ref
  if (typeof ref !== 'string' || !ref.startsWith('#/')) return schema
  let target: unknown = root
  for (const part of ref.slice(2).split('/')) {
    target = isObject(target) ? target[part.replaceAll('~1', '/').replaceAll('~0', '~')] : undefined
  }
  return isObject(target) ? { ...target, ...Object.fromEntries(Object.entries(schema).filter(([key]) => key !== '$ref')) } : schema
}

function schemaType(schema: JsonObject): FieldType {
  const declared = arrayOf(schema.type)?.find((type) => type !== 'null') ?? schema.type
  switch (declared) {
    case 'string':
      return 'string'
    case 'number':
    case 'integer':
      return 'number'
    case 'boolean':
      return 'boolean'
    case 'array':
      return 'array'
    case 'object':
      return 'object'
    default:
      if (isObject(schema.properties)) return 'object'
      const options = arrayOf(schema.enum)
      if (options !== null) {
        const [first] = options
        if (typeof first === 'string') return 'string'
        if (typeof first === 'number') return 'number'
        if (typeof first === 'boolean') return 'boolean'
      }
      return 'unknown'
  }
}

function walk(root: JsonObject, schema: JsonObject, prefix: string, depth: number, into: EventField[]): void {
  if (depth > MAX_DEPTH || !isObject(schema.properties)) return
  for (const [name, raw] of Object.entries(schema.properties)) {
    if (!isObject(raw) || !/^\w+$/.test(name)) continue
    const property = resolveRef(root, raw)
    const path = `${prefix}.${name}`
    const type = schemaType(property)
    into.push({
      path,
      type,
      values: arrayOf(property.enum)?.filter(isScalar) ?? [],
      description: typeof property.description === 'string' ? property.description : null,
    })
    if (type === 'object') walk(root, property, path, depth + 1, into)
  }
}

/** Every `payload.…` path a JSON Schema describes, nested objects included, in schema order. */
export function schemaFields(jsonSchema: JsonObject): EventField[] {
  const fields: EventField[] = []
  walk(jsonSchema, resolveRef(jsonSchema, jsonSchema), 'payload', 0, fields)
  return fields
}

/**
 * The fields of several schemas, metadata first. A path in more than one schema keeps its type when they agree and
 * becomes `unknown` when they don't.
 */
export function mergeFields(schemas: readonly JsonObject[]): EventField[] {
  const byPath = new Map<string, EventField>()
  for (const field of [...METADATA_FIELDS, ...schemas.flatMap(schemaFields)]) {
    const known = byPath.get(field.path)
    if (known === undefined) byPath.set(field.path, field)
    else if (known.type !== field.type) byPath.set(field.path, { ...known, type: 'unknown' })
  }
  return [...byPath.values()]
}

/** Operators that make sense for a field type; an unknown field gets every operator (SPEC §8.1 makes a mismatch `false`). */
export const opsForType = {
  string: ['eq', 'ne', 'in', 'not_in', 'contains', 'glob', 'gt', 'gte', 'lt', 'lte', 'exists'],
  number: ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'not_in', 'exists'],
  boolean: ['eq', 'ne', 'exists'],
  array: ['contains', 'exists'],
  object: ['exists'],
  severity: ['eq', 'ne', 'gte', 'gt', 'lte', 'lt', 'in', 'not_in'],
  unknown: LEAF_OPS,
} as const satisfies Record<FieldType, readonly LeafOp[]>

/** JSON type a new value gets for a field type. */
export const valueTypeForField = {
  string: 'string',
  number: 'number',
  boolean: 'boolean',
  array: 'string',
  object: 'string',
  severity: 'string',
  unknown: 'string',
} as const satisfies Record<FieldType, ValueType>

/** Whether the author picks the value's JSON type: only when the schemas don't say. */
export function picksValueType(type: FieldType): boolean {
  return type === 'unknown' || type === 'array'
}
