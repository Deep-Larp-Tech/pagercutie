import { describe, expect, test } from 'vitest'
import type { JsonObject } from './json-text'
import {
  changeType,
  findPlace,
  findProperty,
  fromJsonSchema,
  moveProperty,
  newNode,
  toJsonSchema,
  updateNode,
  updateProperty,
  type SchemaDraft,
} from './schema-draft'

/** Nested object, list of objects, fixed values, a nullable number and constraints. */
const payment: JsonObject = {
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  type: 'object',
  properties: {
    workflowId: { type: 'string', description: 'Workflow run id', minLength: 1, maxLength: 64, pattern: '^wf-', format: 'uuid' },
    amount: { type: ['number', 'null'], minimum: 0, maximum: 1000000 },
    attempts: { type: 'integer' },
    error: {
      type: 'object',
      properties: { code: { enum: ['TIMEOUT', 'REJECTED'] }, retryable: { type: 'boolean' } },
      required: ['code'],
      additionalProperties: false,
    },
    lines: { type: 'array', items: { type: 'object', properties: { sku: { type: 'string' } } }, minItems: 1, maxItems: 50, uniqueItems: true },
    env: { const: 'prod' },
  },
  required: ['workflowId', 'error'],
}

function read(schema: JsonObject): SchemaDraft {
  const result = fromJsonSchema(schema)
  if (!result.ok) throw new Error(JSON.stringify(result.unsupported))
  return result.draft
}

function build(draft: SchemaDraft): JsonObject {
  const result = toJsonSchema(draft)
  if (!result.ok) throw new Error(JSON.stringify(result.issues))
  return result.schema
}

function idOf(draft: SchemaDraft, name: string): string {
  const visit = (properties: SchemaDraft['root']['properties']): string | undefined => {
    for (const property of properties) {
      if (property.name === name) return property.id
      const node = property.node.type === 'array' ? property.node.items : property.node
      if (node.type === 'object') {
        const found = visit(node.properties)
        if (found !== undefined) return found
      }
    }
    return undefined
  }
  const id = visit(draft.root.properties)
  if (id === undefined) throw new Error(`no field ${name}`)
  return id
}

describe('fromJsonSchema and toJsonSchema', () => {
  test('round-trip nested objects, lists, fixed values, null and constraints unchanged', () => {
    expect(build(read(payment))).toEqual(payment)
  })

  test('a type next to fixed values is read when every value meets it', () => {
    const draft = read({ type: 'object', properties: { code: { type: 'string', enum: ['TIMEOUT', 'REJECTED'] } } })
    expect(build(draft)).toEqual({ type: 'object', properties: { code: { enum: ['TIMEOUT', 'REJECTED'] } } })
  })

  test('the new-schema starter round-trips', () => {
    const starter = {
      $schema: 'https://json-schema.org/draft/2020-12/schema',
      type: 'object',
      properties: { message: { type: 'string', maxLength: 500 } },
      required: ['message'],
    }
    expect(build(read(starter))).toEqual(starter)
  })

  test.each([
    [{ type: 'object', $defs: {}, properties: {} }, '', 'Uses $defs.'],
    [{ type: 'object', properties: { a: { $ref: '#/$defs/x' } } }, '/properties/a', 'Names no type.'],
    [{ type: 'object', properties: { a: { oneOf: [] } } }, '/properties/a', 'Names no type.'],
    [{ type: 'object', properties: { a: { type: ['string', 'number'] } } }, '/properties/a', 'Allows several types (string, number).'],
    [{ type: 'object', properties: { a: { type: 'array', items: [{ type: 'string' }] } } }, '/properties/a', 'Uses items that are not one schema.'],
    [{ type: 'object', properties: { 'a/b': { enum: [{ x: 1 }] } } }, '/properties/a~1b', 'Lists fixed values that are objects or lists, or none at all.'],
    [{ type: 'array' }, '', 'The top level is not an object.'],
    [{ type: 'object', properties: { a: { type: 'string', enum: ['x', 1] } } }, '/properties/a', 'Lists fixed values that its type does not allow.'],
    [{ type: 'object', properties: {}, required: ['a'] }, '', 'Requires fields it does not list (a).'],
  ])('%j is refused at %j', (schema, pointer, message) => {
    const result = fromJsonSchema(schema)
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.unsupported).toContainEqual({ pointer, message })
  })

  test('empty and duplicate names, min above max, bad numbers and an invalid pattern are issues per node', () => {
    let draft = read(payment)
    const attempts = idOf(draft, 'attempts')
    draft = updateProperty(draft, attempts, (property) => ({ ...property, name: 'amount' }))
    draft = updateProperty(draft, idOf(draft, 'env'), (property) => ({ ...property, name: ' ' }))
    const workflow = findProperty(draft, idOf(draft, 'workflowId'))?.node
    if (workflow?.type !== 'string') throw new Error('workflowId is text')
    draft = updateNode(draft, workflow.id, (node) => (node.type === 'string' ? { ...node, minLength: '10', maxLength: '5', pattern: '(' } : node))
    const lines = findProperty(draft, idOf(draft, 'lines'))?.node
    if (lines?.type !== 'array') throw new Error('lines is a list')
    draft = updateNode(draft, lines.id, (node) => (node.type === 'array' ? { ...node, minItems: '1.5' } : node))

    const result = toJsonSchema(draft)
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.issues).toEqual(
      expect.arrayContaining([
        { id: attempts, part: 'name', message: 'Another field here has this name.' },
        { id: workflow.id, part: 'maxLength', message: 'Use a maximum length at least as large as the minimum.' },
        { id: workflow.id, part: 'pattern', message: 'Enter a valid regular expression.' },
        { id: lines.id, part: 'minItems', message: 'Enter a whole number, 0 or more.' },
      ]),
    )
    expect(result.issues.some((issue) => issue.part === 'name' && issue.message === 'Enter a field name.')).toBe(true)
  })

  test('typed numbers keep thousands separators out, and "1" stays text in fixed values', () => {
    let draft = read({ type: 'object', properties: { amount: { type: 'number' }, code: { const: '1' } } })
    const amount = findProperty(draft, idOf(draft, 'amount'))?.node
    if (amount === undefined) throw new Error('amount')
    draft = updateNode(draft, amount.id, (node) => (node.type === 'number' ? { ...node, maximum: '10,000,000' } : node))
    expect(build(draft)).toEqual({ type: 'object', properties: { amount: { type: 'number', maximum: 10000000 }, code: { const: '1' } } })
  })
})

describe('moveProperty', () => {
  test('reorders within an object', () => {
    const draft = read(payment)
    const moved = moveProperty(draft, idOf(draft, 'env'), draft.root.id, 0)
    expect(moved.root.properties.map((property) => property.name)).toEqual(['env', 'workflowId', 'amount', 'attempts', 'error', 'lines'])
    const down = moveProperty(draft, idOf(draft, 'workflowId'), draft.root.id, 2)
    expect(down.root.properties.map((property) => property.name).slice(0, 3)).toEqual(['amount', 'workflowId', 'attempts'])
  })

  test('moves a field into a nested object and into a list item object', () => {
    const draft = read(payment)
    const error = findProperty(draft, idOf(draft, 'error'))?.node
    const lines = findProperty(draft, idOf(draft, 'lines'))?.node
    if (error?.type !== 'object' || lines?.type !== 'array' || lines.items.type !== 'object') throw new Error('shape')
    const intoError = moveProperty(draft, idOf(draft, 'env'), error.id, 1)
    expect(findPlace(intoError, idOf(draft, 'env'))).toEqual({ objectId: error.id, index: 1 })
    const intoLines = moveProperty(draft, idOf(draft, 'env'), lines.items.id, 0)
    expect(findPlace(intoLines, idOf(draft, 'env'))).toEqual({ objectId: lines.items.id, index: 0 })
    expect(build(intoLines)).toMatchObject({ properties: { lines: { items: { properties: { env: { const: 'prod' } } } } } })
  })

  test('refuses to move an object into itself or its own fields', () => {
    const draft = read(payment)
    const error = findProperty(draft, idOf(draft, 'error'))?.node
    if (error?.type !== 'object') throw new Error('error is an object')
    expect(moveProperty(draft, idOf(draft, 'error'), error.id, 0)).toBe(draft)
  })
})

describe('changeType', () => {
  test('object to list keeps the fields as the item object, and back', () => {
    const object = { ...newNode('object'), properties: read(payment).root.properties.slice(0, 1) }
    const list = changeType(object, 'array')
    expect(list.type === 'array' && list.items.type === 'object' && list.items.properties).toEqual(object.properties)
    expect(changeType(list, 'object')).toMatchObject({ id: object.id, type: 'object', properties: object.properties })
  })

  test('keeps the id, description and "can be null"', () => {
    const text = { ...newNode('string'), description: 'Amount', nullable: true }
    expect(changeType(text, 'number')).toMatchObject({ id: text.id, type: 'number', description: 'Amount', nullable: true })
  })
})
