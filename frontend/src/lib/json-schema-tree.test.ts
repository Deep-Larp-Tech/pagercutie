import { describe, expect, test } from 'vitest'
import { constraintLabel, fieldTree, type Constraint, type FieldNode } from './json-schema-tree'

/** `[path, types, required]` of every node, depth first, so a test reads the whole tree at once. */
function outline(nodes: FieldNode[]): [string, string, boolean][] {
  return nodes.flatMap((node) => [[node.path, node.types.join('|'), node.required], ...outline(node.children)])
}

describe('fieldTree', () => {
  test('lists top-level properties with types and required flags, in schema order', () => {
    const tree = fieldTree({
      type: 'object',
      properties: { workflowId: { type: 'string' }, amount: { type: 'number' }, note: { type: ['string', 'null'] } },
      required: ['workflowId'],
    })

    expect(outline(tree)).toEqual([
      ['workflowId', 'string', true],
      ['amount', 'number', false],
      ['note', 'string|null', false],
    ])
  })

  test('nests objects and array items as sub-schemas (SCH-3.1, SCH-3.2)', () => {
    const tree = fieldTree({
      type: 'object',
      properties: {
        error: { type: 'object', properties: { code: { type: 'string' } }, required: ['code'] },
        lines: { type: 'array', items: { type: 'object', properties: { amount: { type: 'integer' } } } },
      },
    })

    expect(outline(tree)).toEqual([
      ['error', 'object', false],
      ['error.code', 'string', true],
      ['lines', 'array', false],
      ['lines[]', 'object', false],
      ['lines[].amount', 'integer', false],
    ])
    expect(tree[1]?.children[0]?.name).toBe('[]')
  })

  test('infers object and array when type is left out', () => {
    const tree = fieldTree({ properties: { meta: { properties: { a: {} } }, tags: { items: { type: 'string' } } } })

    expect(outline(tree)).toEqual([
      ['meta', 'object', false],
      ['meta.a', '', false],
      ['tags', 'array', false],
      ['tags[]', 'string', false],
    ])
  })

  test('reads type-dependent value constraints (SCH-3.3)', () => {
    const [currency, amount, tags, status, kind, created] = fieldTree({
      properties: {
        currency: { type: 'string', minLength: 3, maxLength: 3, pattern: '^[A-Z]+$' },
        amount: { type: 'number', minimum: 0, exclusiveMaximum: 1000000, multipleOf: 0.01 },
        tags: { type: 'array', minItems: 1, maxItems: 5, uniqueItems: true },
        status: { enum: ['TIMEOUT', 'REJECTED'] },
        kind: { const: 'settlement' },
        created: { type: 'string', format: 'date-time' },
      },
    })

    expect(currency?.constraints).toEqual([
      { kind: 'minLength', value: 3 },
      { kind: 'maxLength', value: 3 },
      { kind: 'pattern', value: '^[A-Z]+$' },
    ])
    expect(amount?.constraints).toEqual([
      { kind: 'minimum', value: 0 },
      { kind: 'exclusiveMaximum', value: 1000000 },
      { kind: 'multipleOf', value: 0.01 },
    ])
    expect(tags?.constraints).toEqual([{ kind: 'minItems', value: 1 }, { kind: 'maxItems', value: 5 }, { kind: 'uniqueItems' }])
    expect(status?.constraints).toEqual([{ kind: 'enum', values: ['TIMEOUT', 'REJECTED'] }])
    expect(kind?.constraints).toEqual([{ kind: 'const', value: 'settlement' }])
    expect(created?.constraints).toEqual([{ kind: 'format', value: 'date-time' }])
  })

  test('resolves $ref into $defs and keeps the keywords next to it', () => {
    const [price] = fieldTree({
      $defs: {
        money: {
          type: 'object',
          properties: { amount: { type: 'number' }, currency: { type: 'string', maxLength: 3 } },
          required: ['amount'],
        },
      },
      properties: { price: { $ref: '#/$defs/money', description: 'Charged amount' } },
    })

    expect(price?.ref).toBe('#/$defs/money')
    expect(price?.description).toBe('Charged amount')
    expect(outline(price === undefined ? [] : [price])).toEqual([
      ['price', 'object', false],
      ['price.amount', 'number', true],
      ['price.currency', 'string', false],
    ])
  })

  test('stops at a recursive $ref instead of looping', () => {
    const [node] = fieldTree({
      $defs: { node: { type: 'object', properties: { child: { $ref: '#/$defs/node' } } } },
      properties: { root: { $ref: '#/$defs/node' } },
    })

    const child = node?.children[0]
    expect(child?.path).toBe('root.child')
    expect(child?.recursive).toBe(true)
    expect(child?.children).toEqual([])
  })

  test('marks a $ref outside the document as unresolved', () => {
    const [remote, missing] = fieldTree({
      properties: { remote: { $ref: 'https://example.com/money.json' }, missing: { $ref: '#/$defs/nope' } },
    })

    expect(remote?.unresolved).toBe(true)
    expect(missing?.unresolved).toBe(true)
  })

  test('decodes escaped JSON pointer tokens', () => {
    const [field] = fieldTree({ $defs: { 'a/b': { type: 'string' } }, properties: { x: { $ref: '#/$defs/a~1b' } } })

    expect(field?.types).toEqual(['string'])
  })

  test('shows oneOf and anyOf alternatives as options', () => {
    const [id, value] = fieldTree({
      properties: {
        id: { oneOf: [{ type: 'string' }, { type: 'integer', minimum: 1 }] },
        value: { anyOf: [{ type: 'object', properties: { a: { type: 'string' } } }] },
      },
    })

    expect(id?.combinator).toBe('one of')
    expect(id?.children.map((child) => [child.name, child.types])).toEqual([
      ['option 1', ['string']],
      ['option 2', ['integer']],
    ])
    expect(value?.combinator).toBe('any of')
    expect(outline(value?.children ?? [])).toEqual([
      ['value', 'object', false],
      ['value.a', 'string', false],
    ])
  })

  test('merges allOf parts into one object', () => {
    const tree = fieldTree({
      $defs: { base: { properties: { id: { type: 'string' } }, required: ['id'] } },
      allOf: [{ $ref: '#/$defs/base' }, { properties: { amount: { type: 'number' } } }],
    })

    expect(outline(tree)).toEqual([
      ['id', 'string', true],
      ['amount', 'number', false],
    ])
  })

  test('has no fields for anything but an object schema', () => {
    expect(fieldTree(null)).toEqual([])
    expect(fieldTree([])).toEqual([])
    expect(fieldTree('string')).toEqual([])
    expect(fieldTree({ type: 'object' })).toEqual([])
  })
})

describe('constraintLabel', () => {
  test.each<[Constraint, string]>([
    [{ kind: 'maxLength', value: 3 }, 'at most 3 characters'],
    [{ kind: 'minLength', value: 1 }, 'at least 1 character'],
    [{ kind: 'minimum', value: 1000000 }, 'at least 1,000,000'],
    [{ kind: 'maximum', value: 10 }, 'at most 10'],
    [{ kind: 'exclusiveMinimum', value: 0 }, 'more than 0'],
    [{ kind: 'exclusiveMaximum', value: 5 }, 'less than 5'],
    [{ kind: 'multipleOf', value: 0.5 }, 'multiple of 0.5'],
    [{ kind: 'minItems', value: 2 }, 'at least 2 items'],
    [{ kind: 'maxItems', value: 1 }, 'at most 1 item'],
    [{ kind: 'minProperties', value: 1 }, 'at least 1 field'],
    [{ kind: 'maxProperties', value: 4 }, 'at most 4 fields'],
    [{ kind: 'pattern', value: '^[A-Z]+$' }, 'matches ^[A-Z]+$'],
    [{ kind: 'format', value: 'email' }, 'format email'],
    [{ kind: 'enum', values: ['TIMEOUT', 3] }, 'one of "TIMEOUT", 3'],
    [{ kind: 'const', value: 'x' }, 'always "x"'],
    [{ kind: 'uniqueItems' }, 'no duplicates'],
  ])('%o reads "%s"', (constraint, label) => {
    expect(constraintLabel(constraint)).toBe(label)
  })
})
