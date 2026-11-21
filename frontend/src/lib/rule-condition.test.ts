import { describe, expect, test } from 'vitest'
import type { Condition } from '@/api/generated/model'
import {
  addChild,
  describeCondition,
  fromRootCondition,
  locateIssue,
  newLeaf,
  removeNode,
  toRootCondition,
  updateNode,
  type GroupDraft,
  type LeafDraft,
} from './rule-condition'

/** Team Settlements' condition (SPEC §4.3). */
const settlements: Condition = {
  op: 'and',
  args: [
    { op: 'eq', field: 'payload.type', value: 'WORKFLOW_FAILED' },
    { op: 'eq', field: 'payload.workflowName', value: 'order-settlement' },
    { op: 'eq', field: 'payload.environment', value: 'prod' },
  ],
}

/** The brief's `amount > 1,000,000` or `error.code in [TIMEOUT, REJECTED]`, critical only (SPEC §4.3). */
const nested: Condition = {
  op: 'and',
  args: [
    { op: 'eq', field: 'severity', value: 'critical' },
    {
      op: 'or',
      args: [
        { op: 'gt', field: 'payload.amount', value: 1000000 },
        { op: 'in', field: 'payload.error.code', value: ['TIMEOUT', 'REJECTED'] },
      ],
    },
  ],
}

function roundTrip(condition: Condition) {
  return toRootCondition(fromRootCondition(condition))
}

function leafAt(root: GroupDraft, ...indexes: number[]): LeafDraft {
  let node: GroupDraft['children'][number] = root
  for (const index of indexes) {
    if (node.kind !== 'group') throw new Error('not a group')
    const child: GroupDraft['children'][number] | undefined = node.children[index]
    if (child === undefined) throw new Error('no child')
    node = child
  }
  if (node.kind !== 'leaf') throw new Error('not a leaf')
  return node
}

describe('condition ↔ editor model', () => {
  test.each<[string, Condition]>([
    ['Settlements', settlements],
    ['nested AND / OR with numbers and lists', nested],
    ['a bare predicate (the e2e fixture)', { op: 'exists', field: 'payload.workflowId' }],
    ['a negated predicate', { op: 'not', arg: { op: 'eq', field: 'payload.environment', value: 'test' } }],
    ['a negated group', { op: 'not', arg: { op: 'or', args: [{ op: 'exists', field: 'a' }, { op: 'exists', field: 'b' }] } }],
    ['Pricing: glob and ordered severity', {
      op: 'and',
      args: [
        { op: 'glob', field: 'source', value: 'pricing-engine-*' },
        { op: 'gte', field: 'severity', value: 'warn' },
      ],
    }],
    ['a mixed-type list, booleans and null', {
      op: 'or',
      args: [
        { op: 'in', field: 'payload.code', value: [1, 'two', true, null] },
        { op: 'eq', field: 'payload.retried', value: false },
        { op: 'ne', field: 'payload.owner', value: null },
        { op: 'contains', field: 'payload.tags', value: 'urgent' },
      ],
    }],
  ])('%s round-trips exactly', (_, condition) => {
    expect(roundTrip(condition)).toEqual({ ok: true, condition })
  })

  test('not(not(x)) keeps both negations', () => {
    const condition: Condition = { op: 'not', arg: { op: 'not', arg: { op: 'exists', field: 'a' } } }
    const result = roundTrip(condition)

    expect(result).toEqual({
      ok: true,
      condition: { op: 'not', arg: { op: 'and', args: [{ op: 'not', arg: { op: 'exists', field: 'a' } }] } },
    })
  })

  test('numbers stay numbers and accept grouping', () => {
    const root = fromRootCondition({ op: 'gt', field: 'payload.notional', value: 1 })
    const edited = updateNode(root, leafAt(root, 0).id, (node) =>
      node.kind === 'leaf' ? { ...node, values: [{ type: 'number', text: '10,000,000' }] } : node,
    )

    expect(toRootCondition(edited)).toEqual({ ok: true, condition: { op: 'gt', field: 'payload.notional', value: 10000000 } })
  })

  test('every problem is reported against its node', () => {
    const root = fromRootCondition(settlements)
    const empty: GroupDraft = { kind: 'group', id: 'empty', negated: false, mode: 'or', children: [] }
    let draft = addChild(root, root.id, empty)
    draft = updateNode(draft, leafAt(root, 0).id, (node) => (node.kind === 'leaf' ? { ...node, field: '' } : node))
    draft = updateNode(draft, leafAt(root, 1).id, (node) =>
      node.kind === 'leaf' ? { ...node, op: 'gt', values: [{ type: 'number', text: 'lots' }] } : node,
    )

    const result = toRootCondition(draft)

    expect(result).toEqual({
      ok: false,
      issues: [
        { nodeId: leafAt(root, 0).id, part: 'field', message: 'Pick or type a field.' },
        { nodeId: leafAt(root, 1).id, part: 'value', message: 'Enter a number, e.g. 10000000.' },
        { nodeId: 'empty', part: 'children', message: 'Add at least one condition to this group.' },
      ],
    })
  })

  test('a field path the API rejects is reported', () => {
    const root = fromRootCondition({ op: 'exists', field: 'a' })
    const draft = updateNode(root, leafAt(root, 0).id, (node) => (node.kind === 'leaf' ? { ...node, field: '1bad path' } : node))

    expect(toRootCondition(draft)).toMatchObject({ ok: false, issues: [{ part: 'field' }] })
  })

  test('removeNode drops a nested node; addChild appends', () => {
    const root = fromRootCondition(nested)
    const inner = root.children[1]
    if (inner?.kind !== 'group') throw new Error('expected a group')

    const removed = removeNode(root, leafAt(root, 1, 0).id)
    const added = addChild(removed, inner.id, newLeaf('payload.desk'))

    expect(leafAt(added, 1, 0).field).toBe('payload.error.code')
    expect(leafAt(added, 1, 1).field).toBe('payload.desk')
  })
})

describe('locateIssue', () => {
  test('follows Pydantic paths that include the union tag', () => {
    const root = fromRootCondition({
      op: 'and',
      args: [
        { op: 'eq', field: 'a', value: 1 },
        { op: 'not', arg: { op: 'gt', field: 'b', value: 2 } },
      ],
    })

    expect(locateIssue(root, ['and', 'args', 0, 'eq', 'value'])).toEqual({ nodeId: leafAt(root, 0).id, part: 'value' })
    expect(locateIssue(root, ['and', 'args', 1, 'not', 'arg', 'gt', 'field'])).toEqual({
      nodeId: leafAt(root, 1).id,
      part: 'field',
    })
    expect(locateIssue(root, ['and', 'args'])).toEqual({ nodeId: root.id, part: 'children' })
  })

  test('a single predicate is sent unwrapped, so its path starts at the predicate', () => {
    const root = fromRootCondition({ op: 'in', field: 'a', value: ['x'] })

    expect(locateIssue(root, ['in', 'value', 0])).toEqual({ nodeId: leafAt(root, 0).id, part: 'value' })
  })

  test('a path outside the draft is not placed', () => {
    const root = fromRootCondition(settlements)

    expect(locateIssue(root, ['and', 'args', 9, 'eq', 'value'])).toBeNull()
  })
})

describe('describeCondition', () => {
  test("Team Settlements' condition reads as a sentence", () => {
    expect(describeCondition(fromRootCondition(settlements))).toBe(
      'type is WORKFLOW_FAILED and workflowName is order-settlement and environment is prod',
    )
  })

  test('nested groups go in parentheses, numbers are grouped, lists read as one of', () => {
    expect(describeCondition(fromRootCondition(nested))).toBe(
      'severity is Critical and (amount is more than 1,000,000 or error.code is one of TIMEOUT or REJECTED)',
    )
  })

  test('Team Rates and Pricing', () => {
    expect(
      describeCondition(
        fromRootCondition({
          op: 'and',
          args: [
            { op: 'glob', field: 'payload.type', value: 'trade.rejected.*' },
            { op: 'eq', field: 'payload.desk', value: 'rates' },
            { op: 'gt', field: 'payload.notional', value: 10000000 },
          ],
        }),
      ),
    ).toBe('type matches the pattern trade.rejected.* and desk is rates and notional is more than 10,000,000')
    expect(
      describeCondition(
        fromRootCondition({
          op: 'and',
          args: [
            { op: 'glob', field: 'source', value: 'pricing-engine-*' },
            { op: 'gte', field: 'severity', value: 'warn' },
          ],
        }),
      ),
    ).toBe('source matches the pattern pricing-engine-* and severity is at least Warning')
  })

  test('negation, presence and unfinished parts', () => {
    const root = fromRootCondition({
      op: 'and',
      args: [
        { op: 'not', arg: { op: 'eq', field: 'payload.environment', value: 'test' } },
        { op: 'exists', field: 'payload.error' },
      ],
    })

    expect(describeCondition(root)).toBe('not (environment is test) and error is present')
    expect(describeCondition(addChild(root, root.id, newLeaf()))).toBe(
      'not (environment is test) and error is present and … is …',
    )
    expect(describeCondition({ ...root, children: [] })).toBe('No conditions yet.')
  })
})
