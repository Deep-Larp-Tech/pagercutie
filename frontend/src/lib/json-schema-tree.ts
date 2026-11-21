import { isJsonObject, type JsonObject } from './json-text'

/** Numeric JSON Schema keywords that limit a value (`SCH-3`, type-dependent value constraints). */
export type NumericKeyword =
  | 'minLength'
  | 'maxLength'
  | 'minimum'
  | 'maximum'
  | 'exclusiveMinimum'
  | 'exclusiveMaximum'
  | 'multipleOf'
  | 'minItems'
  | 'maxItems'
  | 'minProperties'
  | 'maxProperties'

/** One value constraint on a field, read from its JSON Schema keywords. */
export type Constraint =
  | { kind: NumericKeyword; value: number }
  /** `pattern`: a regular expression the string must match. */
  | { kind: 'pattern'; value: string }
  /** `format`, e.g. `date-time` or `email`. */
  | { kind: 'format'; value: string }
  /** `enum`: the allowed values, in schema order. */
  | { kind: 'enum'; values: unknown[] }
  /** `const`: the one allowed value. */
  | { kind: 'const'; value: unknown }
  /** `uniqueItems: true`. */
  | { kind: 'uniqueItems' }

/** One field of an event payload as its JSON Schema describes it. */
export interface FieldNode {
  /** Property name; `[]` for the items of an array, `option 1`… for the alternatives of `oneOf` / `anyOf`. */
  name: string
  /** Dotted path from the payload root, e.g. `error.code`; array items add `[]` (`lines[].amount`). */
  path: string
  /** JSON types the schema allows (`string`, `object`, …), in schema order; empty when it names none. */
  types: string[]
  /** Listed in the parent object's `required`. */
  required: boolean
  /** The schema's `description`, if any. */
  description: string | null
  constraints: Constraint[]
  /** Nested fields: object properties, array items or alternatives. */
  children: FieldNode[]
  /** How `children` relate when they are alternatives; `null` for plain properties and items. */
  combinator: 'one of' | 'any of' | null
  /** The `$ref` this field's schema came from, e.g. `#/$defs/money`; `null` when it is inline. */
  ref: string | null
  /** The `$ref` points back at a schema already being expanded, so the children are left out. */
  recursive: boolean
  /** The `$ref` could not be resolved inside the document (an external URL or a missing `$defs` entry). */
  unresolved: boolean
}

const NUMERIC_KEYWORDS = [
  'minLength',
  'maxLength',
  'minimum',
  'maximum',
  'exclusiveMinimum',
  'exclusiveMaximum',
  'multipleOf',
  'minItems',
  'maxItems',
  'minProperties',
  'maxProperties',
] as const satisfies readonly NumericKeyword[]

function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString('en')} ${count === 1 ? one : many}`
}

const numericLabel = {
  minLength: (n) => `at least ${plural(n, 'character', 'characters')}`,
  maxLength: (n) => `at most ${plural(n, 'character', 'characters')}`,
  minimum: (n) => `at least ${n.toLocaleString('en')}`,
  maximum: (n) => `at most ${n.toLocaleString('en')}`,
  exclusiveMinimum: (n) => `more than ${n.toLocaleString('en')}`,
  exclusiveMaximum: (n) => `less than ${n.toLocaleString('en')}`,
  multipleOf: (n) => `multiple of ${n.toLocaleString('en')}`,
  minItems: (n) => `at least ${plural(n, 'item', 'items')}`,
  maxItems: (n) => `at most ${plural(n, 'item', 'items')}`,
  minProperties: (n) => `at least ${plural(n, 'field', 'fields')}`,
  maxProperties: (n) => `at most ${plural(n, 'field', 'fields')}`,
} as const satisfies Record<NumericKeyword, (value: number) => string>

/** A constraint in plain words for the field tree, e.g. "at most 3 characters" (`UI-6`). */
export function constraintLabel(constraint: Constraint): string {
  switch (constraint.kind) {
    case 'pattern':
      return `matches ${constraint.value}`
    case 'format':
      return `format ${constraint.value}`
    case 'enum':
      return `one of ${constraint.values.map((value) => JSON.stringify(value)).join(', ')}`
    case 'const':
      return `always ${JSON.stringify(constraint.value)}`
    case 'uniqueItems':
      return 'no duplicates'
    default:
      return numericLabel[constraint.kind](constraint.value)
  }
}

function constraintsOf(schema: JsonObject): Constraint[] {
  const constraints: Constraint[] = []
  for (const kind of NUMERIC_KEYWORDS) {
    const value = schema[kind]
    if (typeof value === 'number') constraints.push({ kind, value })
  }
  if (typeof schema.pattern === 'string') constraints.push({ kind: 'pattern', value: schema.pattern })
  if (typeof schema.format === 'string') constraints.push({ kind: 'format', value: schema.format })
  if (Array.isArray(schema.enum)) constraints.push({ kind: 'enum', values: schema.enum })
  if ('const' in schema) constraints.push({ kind: 'const', value: schema.const })
  if (schema.uniqueItems === true) constraints.push({ kind: 'uniqueItems' })
  return constraints
}

/** Resolves a same-document JSON pointer (`#/$defs/money`); `undefined` for anything else. */
function resolvePointer(root: JsonObject, ref: string): JsonObject | undefined {
  if (!ref.startsWith('#')) return undefined
  let current: unknown = root
  for (const raw of ref.slice(1).split('/').slice(1)) {
    const token = decodeURIComponent(raw).replaceAll('~1', '/').replaceAll('~0', '~')
    if (Array.isArray(current) && /^\d+$/.test(token)) current = current[Number(token)]
    else if (isJsonObject(current)) current = current[token]
    else return undefined
  }
  return isJsonObject(current) ? current : undefined
}

function typesOf(schema: JsonObject): string[] {
  if (typeof schema.type === 'string') return [schema.type]
  if (Array.isArray(schema.type)) return schema.type.filter((type): type is string => typeof type === 'string')
  if (isJsonObject(schema.properties)) return ['object']
  if (schema.items !== undefined) return ['array']
  return []
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function joinPath(parent: string, name: string): string {
  if (name === '[]') return `${parent}[]`
  return parent === '' ? name : `${parent}.${name}`
}

interface Walk {
  root: JsonObject
  /** `$ref`s being expanded on the way down, to stop at a cycle. */
  expanding: readonly string[]
}

/** Properties and `required` of an object schema, merged over its `allOf` parts. */
function objectParts(schema: JsonObject, walk: Walk): { properties: [string, unknown][]; required: Set<string> } {
  const properties: [string, unknown][] = isJsonObject(schema.properties) ? Object.entries(schema.properties) : []
  const required = new Set(stringList(schema.required))
  if (Array.isArray(schema.allOf)) {
    for (const part of schema.allOf) {
      const resolved = isJsonObject(part) && typeof part.$ref === 'string' ? resolvePointer(walk.root, part.$ref) : part
      if (!isJsonObject(resolved)) continue
      const nested = objectParts(resolved, walk)
      for (const entry of nested.properties) {
        if (!properties.some(([name]) => name === entry[0])) properties.push(entry)
      }
      for (const name of nested.required) required.add(name)
    }
  }
  return { properties, required }
}

function childrenOf(schema: JsonObject, path: string, walk: Walk): Pick<FieldNode, 'children' | 'combinator'> {
  const alternatives = Array.isArray(schema.oneOf) ? schema.oneOf : Array.isArray(schema.anyOf) ? schema.anyOf : null
  if (alternatives !== null) {
    return {
      combinator: Array.isArray(schema.oneOf) ? 'one of' : 'any of',
      children: alternatives.map((alternative, index) => node(`option ${index + 1}`, path, alternative, false, walk)),
    }
  }
  const { properties, required } = objectParts(schema, walk)
  const children = properties.map(([name, child]) => node(name, joinPath(path, name), child, required.has(name), walk))
  if (schema.items !== undefined && schema.items !== true && schema.items !== false) {
    children.push(node('[]', joinPath(path, '[]'), schema.items, false, walk))
  }
  return { children, combinator: null }
}

function node(name: string, path: string, raw: unknown, required: boolean, walk: Walk): FieldNode {
  const base: FieldNode = {
    name,
    path,
    types: [],
    required,
    description: null,
    constraints: [],
    children: [],
    combinator: null,
    ref: null,
    recursive: false,
    unresolved: false,
  }
  if (!isJsonObject(raw)) return base

  let schema = raw
  let { expanding } = walk
  if (typeof raw.$ref === 'string') {
    const ref = raw.$ref
    base.ref = ref
    if (expanding.includes(ref)) return { ...base, recursive: true, description: stringOrNull(raw.description) }
    const target = resolvePointer(walk.root, ref)
    if (target === undefined) return { ...base, unresolved: true, description: stringOrNull(raw.description) }
    schema = { ...target, ...raw }
    expanding = [...expanding, ref]
  }

  return {
    ...base,
    types: typesOf(schema),
    description: stringOrNull(schema.description),
    constraints: constraintsOf(schema),
    ...childrenOf(schema, path, { root: walk.root, expanding }),
  }
}

function stringOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

/**
 * The fields of an event payload as a JSON Schema 2020-12 document describes them (`SCH-3`): nested objects
 * (`properties`, merged over `allOf`), array `items`, `oneOf` / `anyOf` alternatives, same-document `$ref`s into
 * `$defs` (a cycle stops at the repeated `$ref`), types and value constraints. Anything that is not a JSON object
 * has no fields.
 */
export function fieldTree(schema: unknown): FieldNode[] {
  if (!isJsonObject(schema)) return []
  return node('', '', schema, false, { root: schema, expanding: [] }).children
}
