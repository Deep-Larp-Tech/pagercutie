import type { And, Condition, Or, Scalar } from '@/api/generated/model'
import { Severity } from '@/api/generated/model'
import { createRuleBodyConditionFourFieldMax, createRuleBodyConditionFourFieldRegExp } from '@/api/generated/rules/rules.zod'
import { severityLabel } from './severity'

/** A predicate operator: every `Condition` op except the groups and `not` (SPEC §4.3). */
export type LeafOp = Exclude<Condition['op'], And['op'] | Or['op'] | 'not'>

/** How a group combines its children: all of them (`and`) or any of them (`or`). */
export type GroupMode = And['op'] | Or['op']

/** JSON type of a value the author typed; `null` is the JSON `null`. */
export type ValueType = 'string' | 'number' | 'boolean' | 'null'

/** One value as the author typed it, with the JSON type it is sent as. */
export interface ValueDraft {
  type: ValueType
  /** Raw text; `true` or `false` for booleans, ignored for `null`. */
  text: string
}

/** One predicate in the editor. `values` holds one value for comparisons, several for `in`, none for `exists`. */
export interface LeafDraft {
  kind: 'leaf'
  /** Stable id for React keys and error placement; never sent. */
  id: string
  /** Wrapped in `not` when sent. */
  negated: boolean
  /** Dot path into the event, e.g. `payload.error.code`. */
  field: string
  op: LeafOp
  values: ValueDraft[]
}

/** An AND or OR group in the editor. */
export interface GroupDraft {
  kind: 'group'
  id: string
  negated: boolean
  mode: GroupMode
  children: ConditionDraft[]
}

/** The condition tree the editor edits; `toCondition` turns it into the AST the API takes. */
export type ConditionDraft = LeafDraft | GroupDraft

/** Part of a node an error points at. */
export type NodePart = 'field' | 'value' | 'children'

/** A problem with one node of the draft. */
export interface ConditionIssue {
  nodeId: string
  part: NodePart
  message: string
}

/** The result of `toCondition`: the AST, or every problem that stops it from being built. */
export type ConditionResult = { ok: true; condition: Condition } | { ok: false; issues: ConditionIssue[] }

let lastId = 0

/** A fresh node id. */
export function newNodeId(): string {
  lastId += 1
  return `node-${lastId}`
}

/** An empty predicate: `field` `is` (nothing yet). */
export function newLeaf(field = ''): LeafDraft {
  return { kind: 'leaf', id: newNodeId(), negated: false, field, op: 'eq', values: [{ type: 'string', text: '' }] }
}

/** A group with one empty predicate. */
export function newGroup(mode: GroupMode = 'and'): GroupDraft {
  return { kind: 'group', id: newNodeId(), negated: false, mode, children: [newLeaf()] }
}

/** Every op, so maps over leaf ops stay exhaustive. */
export const LEAF_OPS = [
  'eq',
  'ne',
  'gt',
  'gte',
  'lt',
  'lte',
  'in',
  'not_in',
  'contains',
  'glob',
  'exists',
] as const satisfies readonly LeafOp[]

/** How many values an operator takes. */
export const opArity = {
  eq: 'one',
  ne: 'one',
  gt: 'one',
  gte: 'one',
  lt: 'one',
  lte: 'one',
  in: 'many',
  not_in: 'many',
  contains: 'one',
  glob: 'one',
  exists: 'none',
} as const satisfies Record<LeafOp, 'none' | 'one' | 'many'>

function scalarDraft(value: Scalar | null): ValueDraft {
  if (value === null) return { type: 'null', text: '' }
  switch (typeof value) {
    case 'string':
      return { type: 'string', text: value }
    case 'number':
      return { type: 'number', text: String(value) }
    case 'boolean':
      return { type: 'boolean', text: String(value) }
    default:
      return value satisfies never
  }
}

/** The editor node for one AST node. A `not` becomes the `negated` flag of its child; `not(not(x))` keeps a group. */
export function fromCondition(condition: Condition): ConditionDraft {
  const base = { id: newNodeId(), negated: false }
  switch (condition.op) {
    case 'and':
    case 'or':
      return { ...base, kind: 'group', mode: condition.op, children: condition.args.map(fromCondition) }
    case 'not': {
      const inner = fromCondition(condition.arg)
      if (!inner.negated) return { ...inner, negated: true }
      return { ...base, kind: 'group', negated: true, mode: 'and', children: [inner] }
    }
    case 'eq':
    case 'ne':
    case 'gt':
    case 'gte':
    case 'lt':
    case 'lte':
    case 'contains':
      return { ...base, kind: 'leaf', field: condition.field, op: condition.op, values: [scalarDraft(condition.value)] }
    case 'in':
    case 'not_in':
      return { ...base, kind: 'leaf', field: condition.field, op: condition.op, values: condition.value.map(scalarDraft) }
    case 'glob':
      return { ...base, kind: 'leaf', field: condition.field, op: 'glob', values: [{ type: 'string', text: condition.value }] }
    case 'exists':
      return { ...base, kind: 'leaf', field: condition.field, op: 'exists', values: [] }
    default:
      return condition satisfies never
  }
}

/**
 * The editor's root for a rule's condition. The editor always shows a group at the top, so a condition that is not an
 * un-negated group is wrapped in an AND group of one; `toRootCondition` unwraps it again.
 */
export function fromRootCondition(condition: Condition): GroupDraft {
  const node = fromCondition(condition)
  if (node.kind === 'group' && !node.negated) return node
  return { kind: 'group', id: newNodeId(), negated: false, mode: 'and', children: [node] }
}

/** Whether `toRootCondition` sends the root group's only child instead of the group. */
function unwrapsRoot(root: GroupDraft): boolean {
  return !root.negated && root.children.length === 1
}

/** The value as JSON, or a message saying why the text is not a value of its type. */
export function parseValue(value: ValueDraft): { ok: true; value: Scalar | null } | { ok: false; message: string } {
  switch (value.type) {
    case 'string':
      return value.text === '' ? { ok: false, message: 'Enter a value.' } : { ok: true, value: value.text }
    case 'number': {
      const text = value.text.replaceAll(/[\s,_]/g, '')
      const number = Number(text)
      return text === '' || !Number.isFinite(number)
        ? { ok: false, message: 'Enter a number, e.g. 10000000.' }
        : { ok: true, value: number }
    }
    case 'boolean':
      return value.text === 'true' || value.text === 'false'
        ? { ok: true, value: value.text === 'true' }
        : { ok: false, message: 'Pick true or false.' }
    case 'null':
      return { ok: true, value: null }
    default:
      return value.type satisfies never
  }
}

/** Why `path` is not a field path the API accepts, or `null` when it is fine. */
export function fieldPathProblem(path: string): string | null {
  if (path === '') return 'Pick or type a field.'
  if (path.length > createRuleBodyConditionFourFieldMax) {
    return `Use a field path of at most ${createRuleBodyConditionFourFieldMax} characters.`
  }
  if (!createRuleBodyConditionFourFieldRegExp.test(path)) {
    return 'Use a dot path of letters, digits and underscores, e.g. payload.error.code.'
  }
  return null
}

function leafCondition(leaf: LeafDraft, issues: ConditionIssue[]): Condition | null {
  const fieldProblem = fieldPathProblem(leaf.field)
  if (fieldProblem !== null) issues.push({ nodeId: leaf.id, part: 'field', message: fieldProblem })
  const parsed: (Scalar | null)[] = []
  const wanted = opArity[leaf.op] === 'none' ? [] : opArity[leaf.op] === 'one' ? leaf.values.slice(0, 1) : leaf.values
  if (opArity[leaf.op] !== 'none' && wanted.length === 0) {
    issues.push({ nodeId: leaf.id, part: 'value', message: 'Add at least one value.' })
  }
  for (const value of wanted) {
    const result = parseValue(value)
    if (result.ok) parsed.push(result.value)
    else {
      issues.push({ nodeId: leaf.id, part: 'value', message: result.message })
      break
    }
  }
  if (issues.some(({ nodeId }) => nodeId === leaf.id)) return null

  const field = leaf.field
  const [first = null] = parsed
  switch (leaf.op) {
    case 'eq':
    case 'ne':
    case 'gt':
    case 'gte':
    case 'lt':
    case 'lte':
    case 'contains':
      return { op: leaf.op, field, value: first }
    case 'in':
    case 'not_in':
      return { op: leaf.op, field, value: parsed }
    case 'glob':
      if (typeof first !== 'string') {
        issues.push({ nodeId: leaf.id, part: 'value', message: 'Enter a pattern, e.g. pricing-engine-*.' })
        return null
      }
      return { op: 'glob', field, value: first }
    case 'exists':
      return { op: 'exists', field }
    default:
      return leaf.op satisfies never
  }
}

function nodeCondition(node: ConditionDraft, issues: ConditionIssue[]): Condition | null {
  let condition: Condition | null
  if (node.kind === 'leaf') condition = leafCondition(node, issues)
  else {
    if (node.children.length === 0) {
      issues.push({ nodeId: node.id, part: 'children', message: 'Add at least one condition to this group.' })
    }
    const args = node.children.map((child) => nodeCondition(child, issues))
    const built = args.filter((arg): arg is Condition => arg !== null)
    condition = built.length === args.length && built.length > 0 ? { op: node.mode, args: built } : null
  }
  if (condition === null) return null
  return node.negated ? { op: 'not', arg: condition } : condition
}

/** The AST for an editor node, or every problem that stops it from being built. */
export function toCondition(node: ConditionDraft): ConditionResult {
  const issues: ConditionIssue[] = []
  const condition = nodeCondition(node, issues)
  return condition === null || issues.length > 0 ? { ok: false, issues } : { ok: true, condition }
}

/** The AST for the editor's root group; a root group of one child sends the child alone (see `fromRootCondition`). */
export function toRootCondition(root: GroupDraft): ConditionResult {
  const [only] = root.children
  return unwrapsRoot(root) && only !== undefined ? toCondition(only) : toCondition(root)
}

/** Where a FastAPI `422` `loc` below `condition` points in the draft. */
export interface NodeLocation {
  nodeId: string
  part: NodePart
}

const conditionOps: ReadonlySet<string> = new Set<Condition['op']>(['and', 'or', 'not', ...LEAF_OPS])

/**
 * The node and part a `422` error path below `condition` names. Pydantic puts the union tag into the path
 * (`['and', 'args', 0, 'eq', 'value']`), so op names are skipped. `null` when the path leaves the draft.
 */
export function locateIssue(root: GroupDraft, path: readonly (string | number)[]): NodeLocation | null {
  const [only] = root.children
  let node: ConditionDraft = unwrapsRoot(root) && only !== undefined ? only : root
  let part: NodePart = node.kind === 'group' ? 'children' : 'value'
  for (let index = 0; index < path.length; index += 1) {
    const segment = path[index]
    if (typeof segment === 'string' && conditionOps.has(segment)) continue
    if (segment === 'arg') continue
    if (segment === 'args') {
      const position = path[index + 1]
      if (node.kind !== 'group') return null
      if (typeof position !== 'number') {
        part = 'children'
        continue
      }
      const child: ConditionDraft | undefined = node.children[position]
      if (child === undefined) return null
      node = child
      part = node.kind === 'group' ? 'children' : 'value'
      index += 1
      continue
    }
    if (segment === 'field') part = 'field'
    else if (segment === 'value') part = 'value'
    else if (typeof segment === 'number' && part === 'value') continue
    else return null
  }
  return { nodeId: node.id, part }
}

/** Finds the node with `id`. */
export function findNode(node: ConditionDraft, id: string): ConditionDraft | undefined {
  if (node.id === id) return node
  if (node.kind === 'leaf') return undefined
  for (const child of node.children) {
    const found = findNode(child, id)
    if (found !== undefined) return found
  }
  return undefined
}

/** A copy of the tree with the node `id` replaced by `update(node)`. */
export function updateNode(root: GroupDraft, id: string, update: (node: ConditionDraft) => ConditionDraft): GroupDraft {
  const visit = (node: ConditionDraft): ConditionDraft => {
    if (node.id === id) return update(node)
    if (node.kind === 'leaf') return node
    return { ...node, children: node.children.map(visit) }
  }
  const next = visit(root)
  return next.kind === 'group' ? next : root
}

/** A copy of the tree with `child` appended to the group `groupId`. */
export function addChild(root: GroupDraft, groupId: string, child: ConditionDraft): GroupDraft {
  return updateNode(root, groupId, (node) => (node.kind === 'group' ? { ...node, children: [...node.children, child] } : node))
}

/** A copy of the tree without the node `id`; the root itself cannot be removed. */
export function removeNode(root: GroupDraft, id: string): GroupDraft {
  const visit = (group: GroupDraft): GroupDraft => ({
    ...group,
    children: group.children
      .filter((child) => child.id !== id)
      .map((child) => (child.kind === 'group' ? visit(child) : child)),
  })
  return visit(root)
}

/** Field paths are shown without the `payload.` root, as people read the event: `workflowName`, `error.code`. */
export function fieldLabel(path: string): string {
  return path.startsWith('payload.') ? path.slice('payload.'.length) : path
}

/** Words for each operator, as in "amount is more than 1,000,000" (`UI-6`). */
export const opLabel = {
  eq: 'is',
  ne: 'is not',
  gt: 'is more than',
  gte: 'is at least',
  lt: 'is less than',
  lte: 'is at most',
  in: 'is one of',
  not_in: 'is not one of',
  contains: 'contains',
  glob: 'matches the pattern',
  exists: 'is present',
} as const satisfies Record<LeafOp, string>

/** Whether `text` is a `Severity` value. */
export function isSeverity(text: string): text is Severity {
  return Object.values<string>(Severity).includes(text)
}

function describeValue(field: string, value: ValueDraft): string {
  switch (value.type) {
    case 'string':
      if (value.text === '') return '…'
      return field === 'severity' && isSeverity(value.text) ? severityLabel[value.text] : value.text
    case 'number': {
      const number = Number(value.text.replaceAll(/[\s,_]/g, ''))
      return value.text.trim() === '' || !Number.isFinite(number) ? value.text || '…' : number.toLocaleString('en')
    }
    case 'boolean':
      return value.text === '' ? '…' : value.text
    case 'null':
      return 'empty'
    default:
      return value.type satisfies never
  }
}

function joinList(items: readonly string[], conjunction: string): string {
  if (items.length <= 1) return items[0] ?? '…'
  return `${items.slice(0, -1).join(', ')} ${conjunction} ${items.at(-1)}`
}

function describeLeaf(leaf: LeafDraft): string {
  const field = leaf.field === '' ? '…' : fieldLabel(leaf.field)
  const arity = opArity[leaf.op]
  switch (arity) {
    case 'none':
      return `${field} ${opLabel[leaf.op]}`
    case 'one':
      return `${field} ${opLabel[leaf.op]} ${describeValue(leaf.field, leaf.values[0] ?? { type: 'string', text: '' })}`
    case 'many':
      return `${field} ${opLabel[leaf.op]} ${joinList(leaf.values.map((value) => describeValue(leaf.field, value)), 'or')}`
    default:
      return arity satisfies never
  }
}

function describeNode(node: ConditionDraft, nested: boolean): string {
  let text: string
  if (node.kind === 'leaf') text = describeLeaf(node)
  else if (node.children.length === 0) text = 'nothing yet'
  else {
    text = node.children.map((child) => describeNode(child, true)).join(` ${node.mode} `)
    if (nested && node.children.length > 1 && !node.negated) text = `(${text})`
  }
  return node.negated ? `not (${text})` : text
}

/**
 * The condition as one plain sentence (`UI-6`), e.g. "type is WORKFLOW_FAILED and workflowName is order-settlement
 * and environment is prod". Nested groups go in parentheses; unfinished parts show as "…".
 */
export function describeCondition(root: GroupDraft): string {
  if (root.children.length === 0) return 'No conditions yet.'
  return describeNode(root, false)
}
