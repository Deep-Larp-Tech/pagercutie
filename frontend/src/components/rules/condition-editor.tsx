import { useId, useState } from 'react'
import { Plus, Trash2, X } from 'lucide-react'
import type { Severity } from '@/api/generated/model'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { opsForType, picksValueType, valueTypeForField, type EventField, type FieldType } from '@/lib/event-fields'
import {
  addChild,
  describeCondition,
  isSeverity,
  newGroup,
  newLeaf,
  opArity,
  opLabel,
  removeNode,
  updateNode,
  type ConditionDraft,
  type GroupDraft,
  type GroupMode,
  type LeafDraft,
  type LeafOp,
  type ValueDraft,
  type ValueType,
} from '@/lib/rule-condition'
import type { NodeErrors } from '@/lib/rule-draft'
import { severityLabel } from '@/lib/severity'
import { cn } from '@/lib/utils'
import { FieldPathInput } from './field-path-input'

/** How a group reads in the editor. */
const modeLabel = {
  and: 'all of these are true',
  or: 'any of these is true',
} as const satisfies Record<GroupMode, string>

const modeItems = (['and', 'or'] as const).map((mode) => ({ value: mode, label: modeLabel[mode] }))

/** Name of each value type in the type picker. */
const valueTypeLabel = {
  string: 'Text',
  number: 'Number',
  boolean: 'Yes or no',
  null: 'Empty (null)',
} as const satisfies Record<ValueType, string>

const valueTypeItems = (['string', 'number', 'boolean', 'null'] as const).map((type) => ({
  value: type,
  label: valueTypeLabel[type],
}))

/** Most severe first, as people read the list. */
const SEVERITIES: readonly Severity[] = ['critical', 'error', 'warn', 'info', 'debug']

/** Props for `ConditionEditor`. */
export interface ConditionEditorProps {
  value: GroupDraft
  onChange: (value: GroupDraft) => void
  /** Field suggestions from the selected event schemas and the event metadata. */
  fields: readonly EventField[]
  /** Errors per node id, from the client check or a `422`. */
  errors: Partial<Record<string, NodeErrors>>
  readOnly: boolean
}

interface NodeProps {
  root: GroupDraft
  onChange: (value: GroupDraft) => void
  fields: readonly EventField[]
  errors: Partial<Record<string, NodeErrors>>
  readOnly: boolean
}

/**
 * The rule's condition as nested AND / OR groups of predicates (`RUL-1`, `RUL-2`). Each predicate picks a field (with
 * suggestions from the event schemas), an operator the field's type allows and a value typed by the operator; any
 * node can be turned around with **Not**. The whole condition is repeated below as one sentence (`UI-6`).
 */
export function ConditionEditor({ value, onChange, fields, errors, readOnly }: ConditionEditorProps) {
  return (
    <div className="flex flex-col gap-4">
      <GroupEditor group={value} label="" depth={0} root={value} onChange={onChange} fields={fields} errors={errors} readOnly={readOnly} />
      <div className="flex flex-col gap-1 rounded-lg bg-muted px-3 py-2">
        <span className="text-[12px]/[16px] font-medium text-muted-foreground">In words</span>
        <p aria-live="polite" data-testid="condition-sentence">
          {describeCondition(value)}
        </p>
      </div>
    </div>
  )
}

interface GroupEditorProps extends NodeProps {
  group: GroupDraft
  /** Position label, e.g. `2` or `2.1`; empty for the root. */
  label: string
  depth: number
}

function GroupEditor({ group, label, depth, ...props }: GroupEditorProps) {
  const { root, onChange, errors, readOnly } = props
  const isRoot = depth === 0
  const name = isRoot ? 'the rule' : `group ${label}`
  const childError = errors[group.id]?.children
  return (
    <div
      role="group"
      aria-label={isRoot ? 'Condition' : `Group ${label}`}
      className={cn('flex flex-col gap-3', !isRoot && 'rounded-lg border border-dashed p-3')}
    >
      <div className="flex flex-wrap items-center gap-2">
        {group.negated && <NotBadge />}
        <span>{isRoot ? 'Alert when' : 'Match when'}</span>
        <Select
          items={modeItems}
          value={group.mode}
          disabled={readOnly}
          onValueChange={(mode) => mode !== null && onChange(updateNode(root, group.id, (node) => (node.kind === 'group' ? { ...node, mode } : node)))}
        >
          <SelectTrigger aria-label={`How ${name} combines its conditions`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {modeItems.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {!isRoot && !readOnly && (
          <div className="ml-auto flex items-center gap-1">
            <NotToggle node={group} name={name} {...props} />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Remove group ${label}`}
              onClick={() => onChange(removeNode(root, group.id))}
            >
              <Trash2 strokeWidth={1.75} />
            </Button>
          </div>
        )}
      </div>
      {group.children.length > 0 && (
        <ol className="flex flex-col gap-3">
          {group.children.map((child, index) => {
            const childLabel = isRoot ? String(index + 1) : `${label}.${index + 1}`
            return (
              <li key={child.id}>
                {child.kind === 'group' ? (
                  <GroupEditor group={child} label={childLabel} depth={depth + 1} {...props} />
                ) : (
                  <LeafEditor leaf={child} label={childLabel} {...props} />
                )}
              </li>
            )
          })}
        </ol>
      )}
      {childError !== undefined && <NodeError>{childError}</NodeError>}
      {!readOnly && (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            aria-label={isRoot ? 'Add condition' : `Add condition to group ${label}`}
            onClick={() => onChange(addChild(root, group.id, newLeaf()))}
          >
            <Plus strokeWidth={1.75} aria-hidden />
            Add condition
          </Button>
          {depth < 2 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={isRoot ? 'Add group' : `Add group to group ${label}`}
              onClick={() => onChange(addChild(root, group.id, newGroup(group.mode === 'and' ? 'or' : 'and')))}
            >
              <Plus strokeWidth={1.75} aria-hidden />
              Add group
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

function NotBadge() {
  return (
    <span className="rounded-full bg-muted px-2 text-[12px]/[20px] font-medium text-muted-foreground">Not</span>
  )
}

function NotToggle({ node, name, root, onChange }: NodeProps & { node: ConditionDraft; name: string }) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      aria-pressed={node.negated}
      aria-label={`Not: match when ${name} is false`}
      className="aria-pressed:bg-accent aria-pressed:text-primary"
      onClick={() => onChange(updateNode(root, node.id, (current) => ({ ...current, negated: !current.negated })))}
    >
      Not
    </Button>
  )
}

function NodeError({ children }: { children: string }) {
  return <p className="text-[12px]/[16px] font-medium text-alert-red-text">{children}</p>
}

function fieldTypeOf(fields: readonly EventField[], path: string): EventField | undefined {
  return fields.find((field) => field.path === path)
}

/** The leaf's values reshaped for `op`: none for `exists`, one for comparisons, a list for `in`; glob is always text. */
function valuesFor(op: LeafOp, values: readonly ValueDraft[], type: ValueType): ValueDraft[] {
  const first = values[0] ?? { type, text: '' }
  const arity = opArity[op]
  switch (arity) {
    case 'none':
      return []
    case 'one':
      return op === 'glob' ? [{ type: 'string', text: first.text }] : [first]
    case 'many':
      return values.length > 0 ? [...values] : [first]
    default:
      return arity satisfies never
  }
}

interface LeafEditorProps extends NodeProps {
  leaf: LeafDraft
  label: string
}

function LeafEditor({ leaf, label, ...props }: LeafEditorProps) {
  const { root, onChange, fields, errors, readOnly } = props
  const known = fieldTypeOf(fields, leaf.field)
  const fieldType: FieldType = known?.type ?? 'unknown'
  const allowed: readonly LeafOp[] = opsForType[fieldType]
  const ops = allowed.includes(leaf.op) ? allowed : [leaf.op, ...allowed]
  const opItems = ops.map((op) => ({ value: op, label: opLabel[op] }))
  const nodeErrors = errors[leaf.id]
  const update = (change: (leaf: LeafDraft) => LeafDraft) =>
    onChange(updateNode(root, leaf.id, (node) => (node.kind === 'leaf' ? change(node) : node)))

  const setField = (field: string) =>
    update((current) => {
      const type = fieldTypeOf(fields, field)?.type
      if (type === undefined || picksValueType(type)) return { ...current, field }
      const valueType = valueTypeForField[type]
      const op = opsForType[type].some((candidate) => candidate === current.op) ? current.op : opsForType[type][0]
      return { ...current, field, op, values: valuesFor(op, current.values, valueType).map((value) => ({ ...value, type: valueType })) }
    })

  const defaultType = valueTypeForField[fieldType]
  return (
    <div role="group" aria-label={`Condition ${label}`} className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-start gap-2">
        {leaf.negated && <NotBadge />}
        <FieldPathInput
          aria-label={`Field ${label}`}
          className="w-64"
          value={leaf.field}
          onValueChange={setField}
          fields={fields}
          invalid={nodeErrors?.field !== undefined}
          disabled={readOnly}
        />
        <Select
          items={opItems}
          value={leaf.op}
          disabled={readOnly}
          onValueChange={(op) =>
            op !== null && update((current) => ({ ...current, op, values: valuesFor(op, current.values, defaultType) }))
          }
        >
          <SelectTrigger aria-label={`Operator ${label}`} className="min-w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {opItems.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <ValueEditor leaf={leaf} label={label} field={known} fieldType={fieldType} readOnly={readOnly} invalid={nodeErrors?.value !== undefined} onValues={(values) => update((current) => ({ ...current, values }))} />
        {!readOnly && (
          <div className="ml-auto flex items-center gap-1">
            <NotToggle node={leaf} name={`condition ${label}`} {...props} />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Remove condition ${label}`}
              onClick={() => onChange(removeNode(root, leaf.id))}
            >
              <Trash2 strokeWidth={1.75} />
            </Button>
          </div>
        )}
      </div>
      {nodeErrors?.field !== undefined && <NodeError>{nodeErrors.field}</NodeError>}
      {nodeErrors?.value !== undefined && <NodeError>{nodeErrors.value}</NodeError>}
    </div>
  )
}

interface ValueEditorProps {
  leaf: LeafDraft
  label: string
  field: EventField | undefined
  fieldType: FieldType
  readOnly: boolean
  invalid: boolean
  onValues: (values: ValueDraft[]) => void
}

function ValueEditor({ leaf, label, field, fieldType, readOnly, invalid, onValues }: ValueEditorProps) {
  const arity = opArity[leaf.op]
  if (arity === 'none') return null
  const type = leaf.values[0]?.type ?? valueTypeForField[fieldType]
  const typePicker = picksValueType(fieldType) && leaf.op !== 'glob' && (
    <Select
      items={valueTypeItems}
      value={type}
      disabled={readOnly}
      onValueChange={(next) =>
        next !== null &&
        onValues(
          leaf.values.map((value) => ({
            type: next,
            text: next === 'boolean' && value.text !== 'false' ? 'true' : value.text,
          })),
        )
      }
    >
      <SelectTrigger aria-label={`Value type ${label}`}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {valueTypeItems.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
  const suggestions = (field?.values ?? []).filter((value): value is string | number => typeof value === 'string' || typeof value === 'number')

  if (arity === 'many') {
    return (
      <>
        <ValueListInput
          label={label}
          values={leaf.values}
          type={type}
          severity={fieldType === 'severity'}
          suggestions={suggestions}
          readOnly={readOnly}
          invalid={invalid}
          onValues={onValues}
        />
        {typePicker}
      </>
    )
  }
  const value = leaf.values[0] ?? { type, text: '' }
  return (
    <>
      <SingleValueInput
        label={label}
        value={value}
        severity={fieldType === 'severity'}
        suggestions={suggestions}
        readOnly={readOnly}
        invalid={invalid}
        placeholder={leaf.op === 'glob' ? 'e.g. pricing-engine-*' : undefined}
        onValue={(next) => onValues([next])}
      />
      {typePicker}
    </>
  )
}

interface SingleValueInputProps {
  label: string
  value: ValueDraft
  severity: boolean
  suggestions: readonly (string | number)[]
  readOnly: boolean
  invalid: boolean
  placeholder?: string
  onValue: (value: ValueDraft) => void
}

function SingleValueInput({ label, value, severity, suggestions, readOnly, invalid, placeholder, onValue }: SingleValueInputProps) {
  const listId = useId()
  if (severity) {
    const items = SEVERITIES.map((item) => ({ value: item, label: severityLabel[item] }))
    return (
      <Select items={items} value={value.text === '' ? null : value.text} disabled={readOnly} onValueChange={(text) => text !== null && onValue({ type: 'string', text })}>
        <SelectTrigger aria-label={`Value ${label}`} aria-invalid={invalid || undefined} className="min-w-32">
          <SelectValue placeholder="Pick a severity" />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  }
  switch (value.type) {
    case 'boolean': {
      const items = [
        { value: 'true', label: 'true' },
        { value: 'false', label: 'false' },
      ]
      return (
        <Select items={items} value={value.text === '' ? null : value.text} disabled={readOnly} onValueChange={(text) => text !== null && onValue({ type: 'boolean', text })}>
          <SelectTrigger aria-label={`Value ${label}`} aria-invalid={invalid || undefined}>
            <SelectValue placeholder="Pick one" />
          </SelectTrigger>
          <SelectContent>
            {items.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )
    }
    case 'null':
      return <span className="flex h-8 items-center text-muted-foreground">empty</span>
    case 'string':
    case 'number':
      return (
        <>
          <Input
            aria-label={`Value ${label}`}
            aria-invalid={invalid || undefined}
            className="w-48"
            inputMode={value.type === 'number' ? 'decimal' : undefined}
            list={suggestions.length > 0 ? listId : undefined}
            placeholder={placeholder}
            value={value.text}
            disabled={readOnly}
            onChange={(event) => onValue({ type: value.type, text: event.target.value })}
          />
          {suggestions.length > 0 && (
            <datalist id={listId}>
              {suggestions.map((suggestion) => (
                <option key={suggestion} value={suggestion} />
              ))}
            </datalist>
          )}
        </>
      )
    default:
      return value.type satisfies never
  }
}

interface ValueListInputProps {
  label: string
  values: readonly ValueDraft[]
  type: ValueType
  severity: boolean
  suggestions: readonly (string | number)[]
  readOnly: boolean
  invalid: boolean
  onValues: (values: ValueDraft[]) => void
}

/** The values of `in` / `not in` as chips, with an input and **Add**. Empty texts are dropped when a value is added. */
function ValueListInput({ label, values, type, severity, suggestions, readOnly, invalid, onValues }: ValueListInputProps) {
  const [text, setText] = useState('')
  const listId = useId()
  const filled = values.filter((value) => value.type === 'null' || value.text !== '')
  const add = (next: string) => {
    if (next.trim() === '' && type !== 'null') return
    onValues([...filled, { type, text: next.trim() }])
    setText('')
  }
  const display = (value: ValueDraft) => (value.type === 'null' ? 'empty' : severity && isSeverity(value.text) ? severityLabel[value.text] : value.text)

  return (
    <div className="flex flex-col gap-1.5">
      {filled.length > 0 && (
        <ul aria-label={`Values ${label}`} className="flex flex-wrap gap-1.5">
          {filled.map((value, index) => (
            <li key={`${index}-${value.text}`} className="inline-flex h-6 items-center gap-1 rounded-full bg-muted pr-0.5 pl-2.5 text-[12px]/[16px]">
              {display(value)}
              {!readOnly && (
                <button
                  type="button"
                  aria-label={`Remove value ${display(value)}`}
                  className="flex size-5 items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
                  onClick={() => onValues(filled.filter((_, other) => other !== index))}
                >
                  <X className="size-3" strokeWidth={1.75} aria-hidden />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!readOnly && (
        <div className="flex items-center gap-2">
          {severity ? (
            <Select
              items={SEVERITIES.map((item) => ({ value: item, label: severityLabel[item] }))}
              value={null}
              onValueChange={(next) => next !== null && add(next)}
            >
              <SelectTrigger aria-label={`Add value ${label}`} aria-invalid={invalid || undefined}>
                <SelectValue placeholder="Add a severity" />
              </SelectTrigger>
              <SelectContent>
                {SEVERITIES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {severityLabel[item]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <>
              <Input
                aria-label={`Add value ${label}`}
                aria-invalid={invalid || undefined}
                className="w-40"
                list={suggestions.length > 0 ? listId : undefined}
                value={text}
                onChange={(event) => setText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    add(text)
                  }
                }}
              />
              {suggestions.length > 0 && (
                <datalist id={listId}>
                  {suggestions.map((suggestion) => (
                    <option key={suggestion} value={suggestion} />
                  ))}
                </datalist>
              )}
              <Button type="button" variant="secondary" size="sm" aria-label={`Add value to condition ${label}`} onClick={() => add(text)}>
                Add
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
