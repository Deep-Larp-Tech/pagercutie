import type { NumericKeyword, Constraint } from './json-schema-tree'
import { isJsonObject, type JsonObject } from './json-text'
import { newNodeId, parseValue, type ValueDraft } from './rule-condition'

/** What a field holds in the schema builder: a JSON type, or `literal` for fixed values (`const` / `enum`). */
export type DraftType = 'string' | 'number' | 'integer' | 'boolean' | 'null' | 'object' | 'array' | 'literal'

/** Every builder type, in the order the palette and the type picker list them. */
export const DRAFT_TYPES = [
  'string',
  'number',
  'integer',
  'boolean',
  'object',
  'array',
  'literal',
  'null',
] as const satisfies readonly DraftType[]

/** Name of each builder type in the palette and the type picker. */
export const draftTypeLabel = {
  string: 'Text',
  number: 'Number',
  integer: 'Whole number',
  boolean: 'Yes or no',
  null: 'Empty (null)',
  object: 'Object',
  array: 'List',
  literal: 'Fixed values',
} as const satisfies Record<DraftType, string>

/** Text constraint keywords the builder edits. */
export type StringBound = Extract<NumericKeyword, 'minLength' | 'maxLength'>
/** Number constraint keywords the builder edits. */
export type NumberBound = Extract<NumericKeyword, 'minimum' | 'maximum'>
/** List constraint keywords the builder edits. */
export type ItemsBound = Extract<NumericKeyword, 'minItems' | 'maxItems'>

/** A text field; bounds and pattern keep the text the author typed until the schema is built. */
export interface StringDraft {
  type: 'string'
  /** Stable id for React keys and error placement; never sent. */
  id: string
  description: string
  /** Also allows `null` (`type: ["string", "null"]`). */
  nullable: boolean
  minLength: string
  maxLength: string
  /** ECMA-262 regular expression the value must match; empty for none. */
  pattern: string
  /** JSON Schema `format`, e.g. `date-time`; empty for none. */
  format: string
}

/** A number (`number`) or whole number (`integer`) field. */
export interface NumberDraft {
  type: 'number' | 'integer'
  id: string
  description: string
  nullable: boolean
  minimum: string
  maximum: string
}

/** A `true` / `false` field. */
export interface BooleanDraft {
  type: 'boolean'
  id: string
  description: string
  nullable: boolean
}

/** A field that is always `null`. */
export interface NullDraft {
  type: 'null'
  id: string
  description: string
}

/** A nested object (`SCH-3` sub-schema). */
export interface ObjectDraft {
  type: 'object'
  id: string
  description: string
  nullable: boolean
  /** Properties in schema order. */
  properties: PropertyDraft[]
  /** Rejects fields that are not listed (`additionalProperties: false`). */
  closed: boolean
}

/** A list whose items all follow one schema. */
export interface ArrayDraft {
  type: 'array'
  id: string
  description: string
  nullable: boolean
  items: NodeDraft
  minItems: string
  maxItems: string
  uniqueItems: boolean
}

/** A field limited to fixed values: one becomes `const`, several become `enum`. */
export interface LiteralDraft {
  type: 'literal'
  id: string
  description: string
  values: ValueDraft[]
}

/** One schema node in the builder. */
export type NodeDraft = StringDraft | NumberDraft | BooleanDraft | NullDraft | ObjectDraft | ArrayDraft | LiteralDraft

/** One named property of an object. */
export interface PropertyDraft {
  id: string
  name: string
  /** Listed in the parent's `required`; an optional field may be left out of the event. */
  required: boolean
  node: NodeDraft
}

/** The whole event schema in the builder: a top-level object. */
export interface SchemaDraft {
  /** The `$schema` dialect URI, kept as found; `null` when the document has none. */
  dialect: string | null
  root: ObjectDraft
}

/** Part of a node or property an issue points at. */
export type IssuePart = 'name' | StringBound | NumberBound | ItemsBound | 'pattern' | 'values'

/** A problem with one node or property of the draft, keyed by its id. */
export interface DraftIssue {
  id: string
  part: IssuePart
  message: string
}

/** The result of `toJsonSchema`: the JSON Schema, or every problem that stops it from being built. */
export type BuildResult = { ok: true; schema: JsonObject } | { ok: false; issues: DraftIssue[] }

/** Something in a JSON Schema the builder cannot show; the schema stays editable as JSON. */
export interface UnsupportedPart {
  /** JSON pointer to the schema node, e.g. `/properties/error`; empty for the root. */
  pointer: string
  message: string
}

/** The result of `fromJsonSchema`. */
export type ReadResult = { ok: true; draft: SchemaDraft } | { ok: false; unsupported: UnsupportedPart[] }

/** JSON Schema 2020-12, the dialect new schemas declare. */
export const DIALECT_2020_12 = 'https://json-schema.org/draft/2020-12/schema'

function newArray(id: string, items: NodeDraft): ArrayDraft {
  return { type: 'array', id, description: '', nullable: false, items, minItems: '', maxItems: '', uniqueItems: false }
}

/** A new node of `type` with no constraints; a list starts with text items, fixed values with one empty text value. */
export function newNode(type: DraftType): NodeDraft {
  const id = newNodeId()
  switch (type) {
    case 'string':
      return { type, id, description: '', nullable: false, minLength: '', maxLength: '', pattern: '', format: '' }
    case 'number':
    case 'integer':
      return { type, id, description: '', nullable: false, minimum: '', maximum: '' }
    case 'boolean':
      return { type, id, description: '', nullable: false }
    case 'null':
      return { type, id, description: '' }
    case 'object':
      return { type, id, description: '', nullable: false, properties: [], closed: false }
    case 'array':
      return newArray(id, newNode('string'))
    case 'literal':
      return { type, id, description: '', values: [{ type: 'string', text: '' }] }
    default:
      return type satisfies never
  }
}

/** A required property named `name` holding a new node of `type`. */
export function newProperty(name: string, type: DraftType): PropertyDraft {
  return { id: newNodeId(), name, required: true, node: newNode(type) }
}

/** `field`, or `field_2`, `field_3`… when a sibling already has the name. */
export function freeName(object: ObjectDraft, base = 'field'): string {
  const taken = new Set(object.properties.map((property) => property.name))
  if (!taken.has(base)) return base
  let n = 2
  while (taken.has(`${base}_${n}`)) n += 1
  return `${base}_${n}`
}

function nullableOf(node: NodeDraft): boolean {
  return node.type === 'null' || node.type === 'literal' ? false : node.nullable
}

/**
 * `node` as `type`, keeping its id, description and whether it allows `null`. An object becomes a list of objects
 * with the same fields, and a list of objects becomes that object, so switching between them loses no fields.
 */
export function changeType(node: NodeDraft, type: DraftType): NodeDraft {
  if (node.type === type) return node
  if (node.type === 'object' && type === 'array') {
    const items: ObjectDraft = { ...node, id: newNodeId(), description: '', nullable: false }
    return { ...newArray(node.id, items), description: node.description, nullable: node.nullable }
  }
  if (node.type === 'array' && type === 'object' && node.items.type === 'object') {
    return { ...node.items, id: node.id, description: node.description, nullable: node.nullable }
  }
  const next = newNode(type)
  next.id = node.id
  next.description = node.description
  if (next.type !== 'null' && next.type !== 'literal') next.nullable = nullableOf(node)
  return next
}

function mapProperties(node: NodeDraft, map: (property: PropertyDraft) => PropertyDraft): NodeDraft {
  switch (node.type) {
    case 'object':
      return { ...node, properties: node.properties.map(map) }
    case 'array':
      return { ...node, items: mapProperties(node.items, map) }
    default:
      return node
  }
}

/** `node` with `update` applied to the node whose id is `id`, at any depth. */
function updateIn(node: NodeDraft, id: string, update: (node: NodeDraft) => NodeDraft): NodeDraft {
  if (node.id === id) return update(node)
  if (node.type === 'array') return { ...node, items: updateIn(node.items, id, update) }
  if (node.type === 'object') {
    return { ...node, properties: node.properties.map((property) => ({ ...property, node: updateIn(property.node, id, update) })) }
  }
  return node
}

function asObject(node: NodeDraft, fallback: ObjectDraft): ObjectDraft {
  return node.type === 'object' ? node : fallback
}

/** The draft with `update` applied to the node whose id is `id`. */
export function updateNode(draft: SchemaDraft, id: string, update: (node: NodeDraft) => NodeDraft): SchemaDraft {
  return { ...draft, root: asObject(updateIn(draft.root, id, update), draft.root) }
}

/** The draft with `update` applied to the property whose id is `id`. */
export function updateProperty(draft: SchemaDraft, id: string, update: (property: PropertyDraft) => PropertyDraft): SchemaDraft {
  const visit = (property: PropertyDraft): PropertyDraft => {
    const next = property.id === id ? update(property) : property
    return { ...next, node: mapProperties(next.node, visit) }
  }
  return { ...draft, root: { ...draft.root, properties: draft.root.properties.map(visit) } }
}

/** Where a property sits: the id of the object holding it and its index there. */
export interface PropertyPlace {
  objectId: string
  index: number
}

function placeIn(node: NodeDraft, id: string): PropertyPlace | null {
  if (node.type === 'array') return placeIn(node.items, id)
  if (node.type !== 'object') return null
  for (const [index, property] of node.properties.entries()) {
    if (property.id === id) return { objectId: node.id, index }
    const found = placeIn(property.node, id)
    if (found !== null) return found
  }
  return null
}

/** Where the property `id` sits, or `null` when the draft has no such property. */
export function findPlace(draft: SchemaDraft, id: string): PropertyPlace | null {
  return placeIn(draft.root, id)
}

function findPropertyIn(node: NodeDraft, id: string): PropertyDraft | null {
  if (node.type === 'array') return findPropertyIn(node.items, id)
  if (node.type !== 'object') return null
  for (const property of node.properties) {
    if (property.id === id) return property
    const found = findPropertyIn(property.node, id)
    if (found !== null) return found
  }
  return null
}

/** The property whose id is `id`, or `null`. */
export function findProperty(draft: SchemaDraft, id: string): PropertyDraft | null {
  return findPropertyIn(draft.root, id)
}

/** Whether the node `nodeId` is `property`'s node or sits anywhere inside it. */
export function containsNode(property: PropertyDraft, nodeId: string): boolean {
  const visit = (node: NodeDraft): boolean => {
    if (node.id === nodeId) return true
    if (node.type === 'array') return visit(node.items)
    if (node.type === 'object') return node.properties.some((child) => visit(child.node))
    return false
  }
  return visit(property.node)
}

/** The draft with `property` inserted into the object `objectId` at `index` (clamped to the list). */
export function insertProperty(draft: SchemaDraft, objectId: string, index: number, property: PropertyDraft): SchemaDraft {
  return updateNode(draft, objectId, (node) => {
    if (node.type !== 'object') return node
    const properties = [...node.properties]
    properties.splice(Math.max(0, Math.min(index, properties.length)), 0, property)
    return { ...node, properties }
  })
}

/** The draft without the property `id`. */
export function removeProperty(draft: SchemaDraft, id: string): SchemaDraft {
  const place = findPlace(draft, id)
  if (place === null) return draft
  return updateNode(draft, place.objectId, (node) =>
    node.type === 'object' ? { ...node, properties: node.properties.filter((property) => property.id !== id) } : node,
  )
}

/**
 * The draft with the property `id` moved to `index` of the object `objectId`, where `index` counts the target list
 * before the move. Moving a property into itself or one of its own descendants leaves the draft unchanged.
 */
export function moveProperty(draft: SchemaDraft, id: string, objectId: string, index: number): SchemaDraft {
  const property = findProperty(draft, id)
  const from = findPlace(draft, id)
  if (property === null || from === null || containsNode(property, objectId)) return draft
  const target = from.objectId === objectId && from.index < index ? index - 1 : index
  if (from.objectId === objectId && from.index === target) return draft
  return insertProperty(removeProperty(draft, id), objectId, target, property)
}

/** The object that holds the fields of `node`: the node itself, or a list's item object; `null` otherwise. */
export function objectIdOf(node: NodeDraft): string | null {
  if (node.type === 'object') return node.id
  if (node.type === 'array') return objectIdOf(node.items)
  return null
}

function findObjectIn(node: NodeDraft, id: string): ObjectDraft | null {
  if (node.type === 'array') return findObjectIn(node.items, id)
  if (node.type !== 'object') return null
  if (node.id === id) return node
  for (const property of node.properties) {
    const found = findObjectIn(property.node, id)
    if (found !== null) return found
  }
  return null
}

/** The object node whose id is `id`, or `null`. */
export function findObject(draft: SchemaDraft, id: string): ObjectDraft | null {
  return findObjectIn(draft.root, id)
}

/** The property whose node holds the fields of the object `objectId`; `null` for the root or an unknown id. */
export function ownerOf(draft: SchemaDraft, objectId: string): PropertyDraft | null {
  const visit = (node: NodeDraft): PropertyDraft | null => {
    if (node.type === 'array') return visit(node.items)
    if (node.type !== 'object') return null
    for (const property of node.properties) {
      if (objectIdOf(property.node) === objectId) return property
      const found = visit(property.node)
      if (found !== null) return found
    }
    return null
  }
  return visit(draft.root)
}

const COMMON = ['type', 'description'] as const
const ALLOWED = {
  string: [...COMMON, 'minLength', 'maxLength', 'pattern', 'format'],
  number: [...COMMON, 'minimum', 'maximum'],
  integer: [...COMMON, 'minimum', 'maximum'],
  boolean: COMMON,
  null: COMMON,
  object: [...COMMON, 'properties', 'required', 'additionalProperties'],
  array: [...COMMON, 'items', 'minItems', 'maxItems', 'uniqueItems'],
  literal: [...COMMON, 'const', 'enum'],
} as const satisfies Record<DraftType, readonly string[]>

type JsonType = Exclude<DraftType, 'literal'>
const JSON_TYPES: readonly string[] = DRAFT_TYPES.filter((type) => type !== 'literal')

function isJsonType(value: unknown): value is JsonType {
  return typeof value === 'string' && JSON_TYPES.includes(value)
}

function pointerJoin(pointer: string, ...tokens: string[]): string {
  return pointer + tokens.map((token) => `/${token.replaceAll('~', '~0').replaceAll('/', '~1')}`).join('')
}

function boundText(value: unknown): string {
  return typeof value === 'number' ? String(value) : ''
}

/** The literal value as builder text, or `null` for an object or array, which the builder cannot show. */
function valueDraft(value: unknown): ValueDraft | null {
  if (value === null) return { type: 'null', text: '' }
  switch (typeof value) {
    case 'string':
      return { type: 'string', text: value }
    case 'number':
      return { type: 'number', text: String(value) }
    case 'boolean':
      return { type: 'boolean', text: String(value) }
    default:
      return null
  }
}

/** Whether `value` is an instance of the JSON Schema `type` keyword (one name or a list of names). */
function matchesType(value: unknown, type: unknown): boolean {
  if (Array.isArray(type)) return type.some((one) => matchesType(value, one))
  switch (type) {
    case 'null':
      return value === null
    case 'boolean':
      return typeof value === 'boolean'
    case 'string':
      return typeof value === 'string'
    case 'number':
      return typeof value === 'number'
    case 'integer':
      return Number.isInteger(value)
    default:
      return false
  }
}

/** The node's type and whether it allows `null`, or why the builder cannot read it. */
function typeOf(schema: JsonObject): { type: DraftType; nullable: boolean } | string {
  if ('const' in schema || 'enum' in schema) return { type: 'literal', nullable: false }
  const raw = schema.type
  if (isJsonType(raw)) return { type: raw, nullable: false }
  if (Array.isArray(raw)) {
    const types = raw.filter((type) => type !== 'null')
    const [only] = types
    if (types.length === 1 && raw.length === 2 && isJsonType(only) && only !== 'null') return { type: only, nullable: true }
    return `Allows several types (${raw.map(String).join(', ')}).`
  }
  if (raw === undefined) return isJsonObject(schema.properties) ? { type: 'object', nullable: false } : 'Names no type.'
  return `Unknown type ${JSON.stringify(raw)}.`
}

function readNode(raw: unknown, pointer: string, out: UnsupportedPart[]): NodeDraft {
  const fallback = newNode('string')
  if (!isJsonObject(raw)) {
    out.push({ pointer, message: 'Is not a schema object.' })
    return fallback
  }
  const typed = typeOf(raw)
  if (typeof typed === 'string') {
    out.push({ pointer, message: typed })
    return fallback
  }
  const allowed: readonly string[] = ALLOWED[typed.type]
  const extra = Object.keys(raw).filter((key) => !allowed.includes(key))
  if (extra.length > 0) out.push({ pointer, message: `Uses ${extra.join(', ')}.` })

  const node = newNode(typed.type)
  node.description = typeof raw.description === 'string' ? raw.description : ''
  switch (node.type) {
    case 'string':
      return {
        ...node,
        nullable: typed.nullable,
        minLength: boundText(raw.minLength),
        maxLength: boundText(raw.maxLength),
        pattern: typeof raw.pattern === 'string' ? raw.pattern : '',
        format: typeof raw.format === 'string' ? raw.format : '',
      }
    case 'number':
    case 'integer':
      return { ...node, nullable: typed.nullable, minimum: boundText(raw.minimum), maximum: boundText(raw.maximum) }
    case 'boolean':
      return { ...node, nullable: typed.nullable }
    case 'null':
      return node
    case 'object': {
      const properties = isJsonObject(raw.properties) ? Object.entries(raw.properties) : []
      const required = Array.isArray(raw.required) ? raw.required.filter((name) => typeof name === 'string') : []
      const unlisted = required.filter((name) => !properties.some(([property]) => property === name))
      if (unlisted.length > 0) out.push({ pointer, message: `Requires fields it does not list (${unlisted.join(', ')}).` })
      if (typeof raw.additionalProperties !== 'boolean' && raw.additionalProperties !== undefined) {
        out.push({ pointer, message: 'Describes extra fields with a schema (additionalProperties).' })
      }
      return {
        ...node,
        nullable: typed.nullable,
        closed: raw.additionalProperties === false,
        properties: properties.map(([name, child]) => ({
          id: newNodeId(),
          name,
          required: required.includes(name),
          node: readNode(child, pointerJoin(pointer, 'properties', name), out),
        })),
      }
    }
    case 'array':
      if (raw.items !== undefined && !isJsonObject(raw.items)) out.push({ pointer, message: 'Uses items that are not one schema.' })
      return {
        ...node,
        nullable: typed.nullable,
        items: isJsonObject(raw.items) ? readNode(raw.items, pointerJoin(pointer, 'items'), out) : node.items,
        minItems: boundText(raw.minItems),
        maxItems: boundText(raw.maxItems),
        uniqueItems: raw.uniqueItems === true,
      }
    case 'literal': {
      const listed = 'const' in raw ? [raw.const] : Array.isArray(raw.enum) ? raw.enum : []
      const values = listed.map(valueDraft)
      if (values.some((value) => value === null) || values.length === 0) {
        out.push({ pointer, message: 'Lists fixed values that are objects or lists, or none at all.' })
      }
      if (raw.type !== undefined && !listed.every((value) => matchesType(value, raw.type))) {
        out.push({ pointer, message: 'Lists fixed values that its type does not allow.' })
      }
      return { ...node, values: values.filter((value) => value !== null) }
    }
    default:
      return node satisfies never
  }
}

/**
 * The builder draft for a JSON Schema document whose top level is an object, or every part the builder cannot show
 * (`$ref`, `oneOf`, tuples, keywords outside the builder's set). Reading never changes the JSON text; only edits in
 * the builder write it.
 */
export function fromJsonSchema(schema: JsonObject): ReadResult {
  const unsupported: UnsupportedPart[] = []
  const { $schema, ...rest } = schema
  const root = readNode(rest, '', unsupported)
  if ($schema !== undefined && typeof $schema !== 'string') unsupported.push({ pointer: '', message: '$schema is not a URI.' })
  if (root.type !== 'object' || root.nullable) unsupported.push({ pointer: '', message: 'The top level is not an object.' })
  if (unsupported.length > 0 || root.type !== 'object') return { ok: false, unsupported }
  return { ok: true, draft: { dialect: typeof $schema === 'string' ? $schema : null, root } }
}

const COUNT_PROBLEM = 'Enter a whole number, 0 or more.'
const NUMBER_PROBLEM = 'Enter a number, e.g. 1000.'

function readCount(text: string): number | null | string {
  const trimmed = text.trim().replaceAll(/[\s,_]/g, '')
  if (trimmed === '') return null
  return /^\d+$/.test(trimmed) ? Number(trimmed) : COUNT_PROBLEM
}

function readNumber(text: string): number | null | string {
  const trimmed = text.trim().replaceAll(/[\s,_]/g, '')
  if (trimmed === '') return null
  const value = Number(trimmed)
  return Number.isFinite(value) ? value : NUMBER_PROBLEM
}

interface Build {
  issues: DraftIssue[]
}

/** Reads a min/max pair, recording problems; sets the keywords that have a value. */
function bounds<Low extends IssuePart, High extends IssuePart>(
  node: { id: string },
  build: Build,
  out: JsonObject,
  read: (text: string) => number | null | string,
  [low, lowText]: [Low, string],
  [high, highText]: [High, string],
  tooLow: string,
): void {
  const min = read(lowText)
  const max = read(highText)
  if (typeof min === 'string') build.issues.push({ id: node.id, part: low, message: min })
  if (typeof max === 'string') build.issues.push({ id: node.id, part: high, message: max })
  if (typeof min === 'number' && typeof max === 'number' && min > max) build.issues.push({ id: node.id, part: high, message: tooLow })
  if (typeof min === 'number') out[low] = min
  if (typeof max === 'number') out[high] = max
}

function typeKeyword(type: JsonType, nullable: boolean): string | string[] {
  return nullable ? [type, 'null'] : type
}

function buildNode(node: NodeDraft, build: Build): JsonObject {
  const out: JsonObject = {}
  switch (node.type) {
    case 'string':
      out.type = typeKeyword('string', node.nullable)
      if (node.description !== '') out.description = node.description
      bounds(node, build, out, readCount, ['minLength', node.minLength], ['maxLength', node.maxLength], 'Use a maximum length at least as large as the minimum.')
      if (node.pattern !== '') {
        try {
          new RegExp(node.pattern, 'u')
          out.pattern = node.pattern
        } catch {
          build.issues.push({ id: node.id, part: 'pattern', message: 'Enter a valid regular expression.' })
        }
      }
      if (node.format.trim() !== '') out.format = node.format.trim()
      return out
    case 'number':
    case 'integer':
      out.type = typeKeyword(node.type, node.nullable)
      if (node.description !== '') out.description = node.description
      bounds(node, build, out, readNumber, ['minimum', node.minimum], ['maximum', node.maximum], 'Use a maximum at least as large as the minimum.')
      return out
    case 'boolean':
      out.type = typeKeyword('boolean', node.nullable)
      if (node.description !== '') out.description = node.description
      return out
    case 'null':
      out.type = 'null'
      if (node.description !== '') out.description = node.description
      return out
    case 'object': {
      out.type = typeKeyword('object', node.nullable)
      if (node.description !== '') out.description = node.description
      const properties: JsonObject = {}
      const seen = new Set<string>()
      for (const property of node.properties) {
        const name = property.name.trim()
        if (name === '') build.issues.push({ id: property.id, part: 'name', message: 'Enter a field name.' })
        else if (seen.has(name)) build.issues.push({ id: property.id, part: 'name', message: 'Another field here has this name.' })
        seen.add(name)
        properties[name] = buildNode(property.node, build)
      }
      out.properties = properties
      const required = node.properties.filter((property) => property.required).map((property) => property.name.trim())
      if (required.length > 0) out.required = required
      if (node.closed) out.additionalProperties = false
      return out
    }
    case 'array':
      out.type = typeKeyword('array', node.nullable)
      if (node.description !== '') out.description = node.description
      out.items = buildNode(node.items, build)
      bounds(node, build, out, readCount, ['minItems', node.minItems], ['maxItems', node.maxItems], 'Use a maximum at least as large as the minimum.')
      if (node.uniqueItems) out.uniqueItems = true
      return out
    case 'literal': {
      if (node.description !== '') out.description = node.description
      const values: unknown[] = []
      for (const value of node.values) {
        const parsed = parseValue(value)
        if (parsed.ok) values.push(parsed.value)
        else build.issues.push({ id: node.id, part: 'values', message: parsed.message })
      }
      if (node.values.length === 0) build.issues.push({ id: node.id, part: 'values', message: 'Add at least one value.' })
      if (values.length === 1) out.const = values[0]
      else out.enum = values
      return out
    }
    default:
      return node satisfies never
  }
}

/** The JSON Schema document the draft describes, with `$schema` first, or every problem found on the way. */
export function toJsonSchema(draft: SchemaDraft): BuildResult {
  const build: Build = { issues: [] }
  const body = buildNode(draft.root, build)
  if (build.issues.length > 0) return { ok: false, issues: build.issues }
  return { ok: true, schema: draft.dialect === null ? body : { $schema: draft.dialect, ...body } }
}

/** Issues grouped by node or property id, then by part; the first message per part wins. */
export function issuesById(issues: readonly DraftIssue[]): Partial<Record<string, Partial<Record<IssuePart, string>>>> {
  const byId: Partial<Record<string, Partial<Record<IssuePart, string>>>> = {}
  for (const { id, part, message } of issues) {
    const entry = (byId[id] ??= {})
    entry[part] ??= message
  }
  return byId
}

/** The node's constraints as `Constraint`s, for plain-word summaries with `constraintLabel`; unreadable text is skipped. */
export function draftConstraints(node: NodeDraft): Constraint[] {
  const out: Constraint[] = []
  const add = (kind: NumericKeyword, text: string, read: (text: string) => number | null | string) => {
    const value = read(text)
    if (typeof value === 'number') out.push({ kind, value })
  }
  switch (node.type) {
    case 'string':
      add('minLength', node.minLength, readCount)
      add('maxLength', node.maxLength, readCount)
      if (node.pattern !== '') out.push({ kind: 'pattern', value: node.pattern })
      if (node.format.trim() !== '') out.push({ kind: 'format', value: node.format.trim() })
      return out
    case 'number':
    case 'integer':
      add('minimum', node.minimum, readNumber)
      add('maximum', node.maximum, readNumber)
      return out
    case 'array':
      add('minItems', node.minItems, readCount)
      add('maxItems', node.maxItems, readCount)
      if (node.uniqueItems) out.push({ kind: 'uniqueItems' })
      return out
    case 'boolean':
    case 'null':
    case 'object':
    case 'literal':
      return out
    default:
      return node satisfies never
  }
}
