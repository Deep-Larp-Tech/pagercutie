import { Fragment, useId, useState, type ReactNode } from 'react'
import { useDraggable, useDroppable } from '@dnd-kit/core'
import {
  ArrowDown,
  ArrowUp,
  CornerDownRight,
  CornerLeftUp,
  GripVertical,
  MoreHorizontal,
  Plus,
  SlidersHorizontal,
  Trash2,
  X,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { constraintLabel } from '@/lib/json-schema-tree'
import { motionTokens } from '@/lib/motion'
import type { ValueDraft, ValueType } from '@/lib/rule-condition'
import {
  DRAFT_TYPES,
  changeType,
  draftConstraints,
  draftTypeLabel,
  findObject,
  findPlace,
  moveProperty,
  objectIdOf,
  ownerOf,
  removeProperty,
  updateNode,
  updateProperty,
  type ArrayDraft,
  type DraftType,
  type IssuePart,
  type LiteralDraft,
  type NodeDraft,
  type ObjectDraft,
  type PropertyDraft,
} from '@/lib/schema-draft'
import { cn } from '@/lib/utils'
import { joinPath, sourceId, targetId, typeIcon, useBuilder } from './schema-builder-context'

const typeItems = DRAFT_TYPES.map((type) => ({ value: type, label: draftTypeLabel[type] }))

/** Name of each literal value type in its picker. */
const valueTypeLabel = {
  string: 'Text',
  number: 'Number',
  boolean: 'Yes or no',
  null: 'Empty (null)',
} as const satisfies Record<ValueType, string>

const valueTypeItems = (['string', 'number', 'boolean', 'null'] as const).map((type) => ({ value: type, label: valueTypeLabel[type] }))

/** Common JSON Schema formats offered as suggestions; any other format can be typed. */
const FORMATS = ['date-time', 'date', 'time', 'email', 'uri', 'uuid', 'hostname', 'ipv4', 'ipv6'] as const

/** Props for `PropertyList`. */
export interface PropertyListProps {
  object: ObjectDraft
  /** Path of the object from the payload root; empty for the root. */
  path: string
  /** The object sits inside the field being dragged, so nothing can be dropped into it. */
  blocked: boolean
}

/** The fields of one object, with a drop slot before, between and after them. */
export function PropertyList({ object, path, blocked }: PropertyListProps) {
  const { dragging } = useBuilder()
  const listBlocked = blocked || dragging?.node.id === object.id
  if (object.properties.length === 0) {
    return <DropSlot objectId={object.id} index={0} blocked={listBlocked} empty />
  }
  return (
    <ol aria-label={path === '' ? 'Fields' : `Fields of ${path}`} className="flex flex-col">
      <DropSlot objectId={object.id} index={0} blocked={listBlocked} />
      <AnimatePresence initial={false}>
        {object.properties.map((property, index) => (
          <Fragment key={property.id}>
            <FieldRow property={property} object={object} index={index} parentPath={path} blocked={listBlocked} />
            <DropSlot objectId={object.id} index={index + 1} blocked={listBlocked} />
          </Fragment>
        ))}
      </AnimatePresence>
    </ol>
  )
}

interface DropSlotProps {
  objectId: string
  index: number
  blocked: boolean
  /** The object has no fields yet: a dashed area that invites a drop. */
  empty?: boolean
}

/** Where a dragged type or field can land; a violet line shows the spot under the pointer. */
function DropSlot({ objectId, index, blocked, empty = false }: DropSlotProps) {
  const { setNodeRef, isOver, active } = useDroppable({ id: targetId({ objectId, index }), disabled: blocked })
  const over = isOver && !blocked
  if (empty) {
    return (
      <div
        ref={setNodeRef}
        className={cn(
          'rounded-lg border border-dashed px-3 py-2.5 text-[12px]/[16px] text-muted-foreground transition-colors duration-(--duration-fast) ease-standard',
          over && 'border-primary bg-accent text-primary',
          active !== null && !blocked && !over && 'border-primary/40',
        )}
      >
        {active === null ? 'No fields yet. Drag a type here or add a field.' : 'Drop here'}
      </div>
    )
  }
  return (
    <li ref={setNodeRef} aria-hidden className="relative h-2 list-none">
      {over && (
        <motion.span
          initial={{ opacity: 0, scaleX: 0.96 }}
          animate={{ opacity: 1, scaleX: 1 }}
          transition={motionTokens.fast}
          className="absolute inset-x-0 top-1/2 flex -translate-y-1/2 items-center"
        >
          <span className="size-2 shrink-0 rounded-full border-2 border-primary bg-background" />
          <span className="h-0.5 flex-1 rounded-full bg-primary" />
        </motion.span>
      )}
    </li>
  )
}

interface FieldRowProps {
  property: PropertyDraft
  /** The object holding the property. */
  object: ObjectDraft
  index: number
  /** Path of the object holding the property; empty for the root. */
  parentPath: string
  blocked: boolean
}

/** One field: drag handle, name, type, required switch, constraints and, for objects and lists, the nested fields. */
function FieldRow({ property, object, index, parentPath, blocked }: FieldRowProps) {
  const { draft, onChange, issues, added, dragging } = useBuilder()
  const [open, setOpen] = useState(false)
  const { setNodeRef, setActivatorNodeRef, listeners, attributes } = useDraggable({
    id: sourceId({ kind: 'field', propertyId: property.id }),
  })
  const node = property.node
  const Icon = typeIcon[node.type]
  const nameError = issues[property.id]?.name
  const path = joinPath(parentPath, property.name)
  const unnamed = parentPath === '' ? 'unnamed field' : `unnamed field in ${parentPath}`
  const label = property.name.trim() === '' ? unnamed : path
  const isDragged = dragging?.id === property.id
  const setProperty = (update: (property: PropertyDraft) => PropertyDraft) => onChange(updateProperty(draft, property.id, update))

  return (
    <motion.li
      ref={setNodeRef}
      layout="position"
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, transition: motionTokens.exit }}
      transition={motionTokens.spring}
      data-path={path}
      className={cn('list-none rounded-lg border bg-card text-card-foreground', isDragged && 'opacity-40')}
    >
      <div className="flex flex-wrap items-center gap-2 py-1.5 pr-1.5 pl-1">
        <button
          type="button"
          ref={setActivatorNodeRef}
          {...attributes}
          {...listeners}
          // The keyboard path is the row menu's move actions, as in the rotation editor.
          tabIndex={-1}
          aria-hidden
          className="flex h-8 w-6 cursor-grab touch-none items-center justify-center rounded-sm text-muted-foreground hover:text-foreground active:cursor-grabbing"
        >
          <GripVertical size={16} strokeWidth={1.75} />
        </button>
        <Icon size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-muted-foreground" />
        <Input
          aria-label={`Name of ${label}`}
          aria-invalid={nameError !== undefined || undefined}
          autoComplete="off"
          spellCheck={false}
          autoFocus={added === property.id}
          onFocus={(event) => added === property.id && event.currentTarget.select()}
          value={property.name}
          onChange={(event) => setProperty((current) => ({ ...current, name: event.target.value }))}
          className="w-44 font-mono text-[13px]"
        />
        <TypeSelect node={node} label={label} onType={(type) => onChange(updateNode(draft, node.id, (current) => changeType(current, type)))} />
        <label className="flex items-center gap-2 text-[12px]/[16px] font-medium text-muted-foreground">
          <Switch
            aria-label={`${label} is required`}
            checked={property.required}
            onCheckedChange={(required) => setProperty((current) => ({ ...current, required }))}
          />
          <span className={cn(property.required && 'text-primary')}>{property.required ? 'Required' : 'Optional'}</span>
        </label>
        <div className="ml-auto flex items-center gap-1">
          <DetailsToggle node={node} label={label} open={open} onOpen={setOpen} />
          <RowMenu property={property} object={object} index={index} label={label} />
        </div>
      </div>
      {nameError !== undefined && <RowError className="pb-1.5 pl-[76px]">{nameError}</RowError>}
      {!open && <Summary node={node} className="pb-2 pl-[76px]" />}
      {open && <NodeDetails node={node} label={label} />}
      <NodeChildren node={node} path={path} blocked={blocked || isDragged} />
    </motion.li>
  )
}

function RowError({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn('text-[12px]/[16px] font-medium text-alert-red-text', className)}>{children}</p>
}

/** The node's constraints in plain words, e.g. "Can be null · at most 500 characters"; nothing when it has none. */
function Summary({ node, className }: { node: NodeDraft; className?: string }) {
  const notes = [
    ...(node.type !== 'null' && node.type !== 'literal' && node.nullable ? ['can be null'] : []),
    ...(node.type === 'object' && node.closed ? ['only listed fields'] : []),
    ...draftConstraints(node).map(constraintLabel),
  ]
  const description = node.description.trim()
  if (notes.length === 0 && description === '') return null
  return (
    <div className={cn('flex flex-col gap-0.5 pr-3 text-[12px]/[16px] text-muted-foreground', className)}>
      {notes.length > 0 && <span>{notes.join(' · ')}</span>}
      {description !== '' && <span className="truncate">{description}</span>}
    </div>
  )
}

function TypeSelect({ node, label, onType }: { node: NodeDraft; label: string; onType: (type: DraftType) => void }) {
  return (
    <Select items={typeItems} value={node.type} onValueChange={(type) => type !== null && onType(type)}>
      <SelectTrigger aria-label={`Type of ${label}`} className="w-40">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {typeItems.map((item) => {
          const ItemIcon = typeIcon[item.value]
          return (
            <SelectItem key={item.value} value={item.value}>
              <ItemIcon strokeWidth={1.75} aria-hidden />
              {item.label}
            </SelectItem>
          )
        })}
      </SelectContent>
    </Select>
  )
}

/** How many constraints a node has set, for the badge on its details toggle. */
function constraintCount(node: NodeDraft): number {
  const nullable = node.type !== 'null' && node.type !== 'literal' && node.nullable ? 1 : 0
  const closed = node.type === 'object' && node.closed ? 1 : 0
  return draftConstraints(node).length + nullable + closed + (node.description.trim() === '' ? 0 : 1)
}

function DetailsToggle({ node, label, open, onOpen }: { node: NodeDraft; label: string; open: boolean; onOpen: (open: boolean) => void }) {
  const count = constraintCount(node)
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      aria-expanded={open}
      aria-label={`Constraints of ${label}`}
      onClick={() => onOpen(!open)}
      className="aria-expanded:text-primary"
    >
      <SlidersHorizontal strokeWidth={1.75} aria-hidden />
      <span className="hidden sm:inline">Constraints</span>
      {count > 0 && (
        <Badge className="h-4 min-w-4 justify-center px-1 font-mono text-[11px]/[14px] tabular-nums">{count}</Badge>
      )}
    </Button>
  )
}

function RowMenu({ property, object, index, label }: { property: PropertyDraft; object: ObjectDraft; index: number; label: string }) {
  const { draft, onChange } = useBuilder()
  const previous = object.properties[index - 1]
  const intoId = previous === undefined ? null : objectIdOf(previous.node)
  const into = intoId === null ? null : findObject(draft, intoId)
  const owner = ownerOf(draft, object.id)
  const ownerPlace = owner === null ? null : findPlace(draft, owner.id)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button type="button" variant="ghost" size="icon-sm" aria-label={`Actions for ${label}`} />}>
        <MoreHorizontal strokeWidth={1.75} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem disabled={index === 0} onClick={() => onChange(moveProperty(draft, property.id, object.id, index - 1))}>
          <ArrowUp strokeWidth={1.75} />
          Move up
        </DropdownMenuItem>
        <DropdownMenuItem
          disabled={index === object.properties.length - 1}
          onClick={() => onChange(moveProperty(draft, property.id, object.id, index + 2))}
        >
          <ArrowDown strokeWidth={1.75} />
          Move down
        </DropdownMenuItem>
        {into !== null && previous !== undefined && (
          <DropdownMenuItem onClick={() => onChange(moveProperty(draft, property.id, into.id, into.properties.length))}>
            <CornerDownRight strokeWidth={1.75} />
            Move into {previous.name === '' ? 'the field above' : previous.name}
          </DropdownMenuItem>
        )}
        {owner !== null && ownerPlace !== null && (
          <DropdownMenuItem onClick={() => onChange(moveProperty(draft, property.id, ownerPlace.objectId, ownerPlace.index + 1))}>
            <CornerLeftUp strokeWidth={1.75} />
            Move out of {owner.name === '' ? 'this object' : owner.name}
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onClick={() => onChange(removeProperty(draft, property.id))}>
          <Trash2 strokeWidth={1.75} />
          Remove field
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

interface ConstraintInputProps {
  label: string
  /** Accessible name prefix, the field's path. */
  owner: string
  value: string
  error: string | undefined
  onValue: (value: string) => void
  placeholder?: string
  mono?: boolean
  list?: string
  numeric?: boolean
}

function ConstraintInput({ label, owner, value, error, onValue, placeholder, mono = false, list, numeric = false }: ConstraintInputProps) {
  return (
    <Field invalid={error !== undefined} className="gap-1">
      <FieldLabel className="text-[12px]/[16px] text-muted-foreground">{label}</FieldLabel>
      <Input
        aria-label={`${label} of ${owner}`}
        autoComplete="off"
        spellCheck={false}
        inputMode={numeric ? 'decimal' : undefined}
        placeholder={placeholder}
        list={list}
        value={value}
        onChange={(event) => onValue(event.target.value)}
        className={cn((mono || numeric) && 'font-mono text-[13px] tabular-nums')}
      />
      {error !== undefined && <FieldError>{error}</FieldError>}
    </Field>
  )
}

function SwitchRow({ label, checked, onChange, ariaLabel }: { label: string; checked: boolean; onChange: (checked: boolean) => void; ariaLabel: string }) {
  return (
    <label className="flex h-8 items-center gap-2 text-[12px]/[16px] font-medium text-muted-foreground">
      <Switch aria-label={ariaLabel} checked={checked} onCheckedChange={onChange} />
      {label}
    </label>
  )
}

/** Description, "can be null" and the constraints the node's type allows (`SCH-3`). */
function NodeDetails({ node, label }: { node: NodeDraft; label: string }) {
  const { draft, onChange, issues } = useBuilder()
  const formatsId = useId()
  const errors: Partial<Record<IssuePart, string>> = issues[node.id] ?? {}
  const set = (update: (node: NodeDraft) => NodeDraft) => onChange(updateNode(draft, node.id, update))
  const nullable = node.type !== 'null' && node.type !== 'literal' && (
    <SwitchRow
      label="Can be null"
      ariaLabel={`${label} can be null`}
      checked={node.nullable}
      onChange={(checked) => set((current) => (current.type === 'null' || current.type === 'literal' ? current : { ...current, nullable: checked }))}
    />
  )

  const typed = (() => {
    switch (node.type) {
      case 'string': {
        const setText = (key: 'minLength' | 'maxLength' | 'pattern' | 'format') => (value: string) =>
          set((current) => (current.type === 'string' ? { ...current, [key]: value } : current))
        return (
          <>
            <ConstraintInput label="Min length" owner={label} numeric value={node.minLength} error={errors.minLength} onValue={setText('minLength')} />
            <ConstraintInput label="Max length" owner={label} numeric value={node.maxLength} error={errors.maxLength} onValue={setText('maxLength')} />
            <ConstraintInput label="Pattern" owner={label} mono placeholder="^[A-Z]{3}$" value={node.pattern} error={errors.pattern} onValue={setText('pattern')} />
            <ConstraintInput label="Format" owner={label} mono placeholder="date-time" list={formatsId} value={node.format} error={undefined} onValue={setText('format')} />
            <datalist id={formatsId}>
              {FORMATS.map((format) => (
                <option key={format} value={format} />
              ))}
            </datalist>
          </>
        )
      }
      case 'number':
      case 'integer': {
        const setBound = (key: 'minimum' | 'maximum') => (value: string) =>
          set((current) => (current.type === 'number' || current.type === 'integer' ? { ...current, [key]: value } : current))
        return (
          <>
            <ConstraintInput label="Minimum" owner={label} numeric value={node.minimum} error={errors.minimum} onValue={setBound('minimum')} />
            <ConstraintInput label="Maximum" owner={label} numeric value={node.maximum} error={errors.maximum} onValue={setBound('maximum')} />
          </>
        )
      }
      case 'array': {
        const setBound = (key: 'minItems' | 'maxItems') => (value: string) =>
          set((current) => (current.type === 'array' ? { ...current, [key]: value } : current))
        return (
          <>
            <ConstraintInput label="Min items" owner={label} numeric value={node.minItems} error={errors.minItems} onValue={setBound('minItems')} />
            <ConstraintInput label="Max items" owner={label} numeric value={node.maxItems} error={errors.maxItems} onValue={setBound('maxItems')} />
            <SwitchRow
              label="No duplicates"
              ariaLabel={`${label} has no duplicate items`}
              checked={node.uniqueItems}
              onChange={(uniqueItems) => set((current) => (current.type === 'array' ? { ...current, uniqueItems } : current))}
            />
          </>
        )
      }
      case 'object':
        return (
          <SwitchRow
            label="Only listed fields"
            ariaLabel={`${label} rejects fields that are not listed`}
            checked={node.closed}
            onChange={(closed) => set((current) => (current.type === 'object' ? { ...current, closed } : current))}
          />
        )
      case 'boolean':
      case 'null':
      case 'literal':
        return null
      default:
        return node satisfies never
    }
  })()

  return (
    <div className="flex flex-col gap-3 border-t bg-muted/40 px-3 py-3">
      <ConstraintInput
        label="Description"
        owner={label}
        placeholder="What the field means, in one line"
        value={node.description}
        error={undefined}
        onValue={(description) => set((current) => ({ ...current, description }))}
      />
      <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] items-end gap-3">
        {typed}
        {nullable}
      </div>
    </div>
  )
}

/** What sits under a row: an object's fields, a list's item type, or the fixed values. */
function NodeChildren({ node, path, blocked }: { node: NodeDraft; path: string; blocked: boolean }) {
  switch (node.type) {
    case 'object':
      return <NestedFields object={node} path={path} blocked={blocked} />
    case 'array':
      return <ItemsEditor list={node} path={path} blocked={blocked} />
    case 'literal':
      return <LiteralValues node={node} label={path} />
    case 'string':
    case 'number':
    case 'integer':
    case 'boolean':
    case 'null':
      return null
    default:
      return node satisfies never
  }
}

function NestedFields({ object, path, blocked }: { object: ObjectDraft; path: string; blocked: boolean }) {
  const { addField } = useBuilder()
  return (
    <div className="flex flex-col gap-1 border-t px-3 pt-1 pb-3">
      <div className="ml-1 border-l-2 border-border pl-3">
        <PropertyList object={object} path={path} blocked={blocked} />
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="ml-4 w-fit text-muted-foreground"
        aria-label={`Add field to ${path === '' ? 'this object' : path}`}
        onClick={() => addField(object.id, object.properties.length, 'string')}
      >
        <Plus strokeWidth={1.75} aria-hidden />
        Add field
      </Button>
    </div>
  )
}

/** A list's item schema: its type and constraints, and nested fields when the items are objects or lists. */
function ItemsEditor({ list, path, blocked }: { list: ArrayDraft; path: string; blocked: boolean }) {
  const { draft, onChange } = useBuilder()
  const [open, setOpen] = useState(false)
  const items = list.items
  const itemPath = joinPath(path, '[]')
  const label = `items of ${path === '' ? 'the list' : path}`
  return (
    <div className="flex flex-col border-t">
      <div className="flex flex-wrap items-center gap-2 py-1.5 pr-1.5 pl-3">
        <CornerDownRight size={14} strokeWidth={1.75} aria-hidden className="text-muted-foreground" />
        <span className="text-[12px]/[16px] font-medium text-muted-foreground">Each item is</span>
        <TypeSelect node={items} label={label} onType={(type) => onChange(updateNode(draft, items.id, (current) => changeType(current, type)))} />
        <div className="ml-auto">
          <DetailsToggle node={items} label={label} open={open} onOpen={setOpen} />
        </div>
      </div>
      {!open && <Summary node={items} className="pb-2 pl-[38px]" />}
      {open && <NodeDetails node={items} label={label} />}
      <NodeChildren node={items} path={itemPath} blocked={blocked} />
    </div>
  )
}

function LiteralValues({ node, label }: { node: LiteralDraft; label: string }) {
  const { draft, onChange, issues } = useBuilder()
  const error = issues[node.id]?.values
  const setValues = (update: (values: ValueDraft[]) => ValueDraft[]) =>
    onChange(updateNode(draft, node.id, (current) => (current.type === 'literal' ? { ...current, values: update(current.values) } : current)))
  return (
    <div className="flex flex-col gap-2 border-t px-3 py-2.5">
      <span className="text-[12px]/[16px] font-medium text-muted-foreground">
        {node.values.length === 1 ? 'Always this value' : 'One of these values'}
      </span>
      <ul aria-label={`Values of ${label}`} className="flex flex-wrap gap-2">
        {node.values.map((value, index) => (
          <li key={index} className="flex max-w-full min-w-0 items-center gap-1 rounded-lg border bg-background p-1">
            <Select
              items={valueTypeItems}
              value={value.type}
              onValueChange={(type) =>
                type !== null &&
                setValues((values) =>
                  values.map((current, at) => (at === index ? { type, text: type === 'boolean' ? (current.text === 'false' ? 'false' : 'true') : current.text } : current)),
                )
              }
            >
              <SelectTrigger aria-label={`Type of value ${index + 1} of ${label}`} className="h-7 w-28 shrink-0 border-transparent text-[12px]">
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
            <LiteralInput
              value={value}
              label={`Value ${index + 1} of ${label}`}
              invalid={error !== undefined}
              onValue={(next) => setValues((values) => values.map((current, at) => (at === index ? next : current)))}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Remove value ${index + 1} of ${label}`}
              disabled={node.values.length === 1}
              onClick={() => setValues((values) => values.filter((_, at) => at !== index))}
            >
              <X strokeWidth={1.75} />
            </Button>
          </li>
        ))}
        <li>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-9"
            aria-label={`Add value to ${label}`}
            onClick={() => setValues((values) => [...values, { type: values.at(-1)?.type ?? 'string', text: '' }])}
          >
            <Plus strokeWidth={1.75} aria-hidden />
            Add value
          </Button>
        </li>
      </ul>
      {error !== undefined && <RowError>{error}</RowError>}
    </div>
  )
}

function LiteralInput({ value, label, invalid, onValue }: { value: ValueDraft; label: string; invalid: boolean; onValue: (value: ValueDraft) => void }) {
  switch (value.type) {
    case 'boolean':
      return (
        <Select items={[{ value: 'true', label: 'true' }, { value: 'false', label: 'false' }]} value={value.text} onValueChange={(text) => text !== null && onValue({ type: 'boolean', text })}>
          <SelectTrigger aria-label={label} className="h-7 w-24 font-mono text-[13px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="true">true</SelectItem>
            <SelectItem value="false">false</SelectItem>
          </SelectContent>
        </Select>
      )
    case 'null':
      return <span className="flex h-7 items-center px-2 font-mono text-[13px] text-muted-foreground">null</span>
    case 'string':
    case 'number':
      return (
        <Input
          aria-label={label}
          aria-invalid={invalid || undefined}
          autoComplete="off"
          spellCheck={false}
          inputMode={value.type === 'number' ? 'decimal' : undefined}
          placeholder={value.type === 'number' ? '0' : 'TIMEOUT'}
          value={value.text}
          onChange={(event) => onValue({ type: value.type, text: event.target.value })}
          className="h-7 w-36 min-w-0 shrink font-mono text-[13px]"
        />
      )
    default:
      return value.type satisfies never
  }
}
