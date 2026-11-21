import { useMemo, useState } from 'react'
import {
  closestCenter,
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { GripVertical, Plus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { controlTransition, focusRing } from '@/components/ui/styles'
import {
  DRAFT_TYPES,
  draftTypeLabel,
  findObject,
  findProperty,
  freeName,
  insertProperty,
  issuesById,
  moveProperty,
  newProperty,
  type DraftIssue,
  type DraftType,
  type SchemaDraft,
} from '@/lib/schema-draft'
import { cn } from '@/lib/utils'
import {
  BuilderContext,
  readSource,
  readTarget,
  sourceId,
  typeIcon,
  type BuilderState,
  type DragSource,
} from './schema-builder-context'
import { PropertyList } from './schema-field-row'

/** Types offered in the palette; `null` stays in the type picker only, since a field that is always null is rare. */
const PALETTE = DRAFT_TYPES.filter((type) => type !== 'null')

/**
 * Picks the drop slot nearest the pointer: distance from the pointer to each slot's box, ties going to the narrower
 * (more deeply nested) slot, so moving right over an object drops into it. Falls back to `closestCenter` without a
 * pointer.
 */
const nearestSlot: CollisionDetection = (args) => {
  const { pointerCoordinates, droppableContainers, droppableRects } = args
  if (pointerCoordinates === null) return closestCenter(args)
  const { x, y } = pointerCoordinates
  return droppableContainers
    .flatMap((container) => {
      const rect = droppableRects.get(container.id)
      if (rect === undefined) return []
      const dx = Math.max(rect.left - x, 0, x - rect.right)
      const dy = Math.max(rect.top - y, 0, y - rect.bottom)
      return [{ id: container.id, data: { droppableContainer: container, value: Math.hypot(dx, dy) * 10_000 + rect.width } }]
    })
    .sort((a, b) => a.data.value - b.data.value)
    .slice(0, 1)
}

/** Props for `SchemaBuilder`. */
export interface SchemaBuilderProps {
  value: SchemaDraft
  onChange: (value: SchemaDraft) => void
  /** Problems from `toJsonSchema`, shown under the fields they belong to. */
  issues: readonly DraftIssue[]
}

/**
 * Visual editor for an event schema (`SCH-3`): drag a type from the palette into the fields, drag a field by its
 * handle to reorder it or move it into or out of a nested object, and set each field's name, type, whether it is
 * required and its constraints. Every move also has a menu action, which is the keyboard path.
 */
export function SchemaBuilder({ value, onChange, issues }: SchemaBuilderProps) {
  const [active, setActive] = useState<DragSource | null>(null)
  const [added, setAdded] = useState<string | null>(null)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }))
  const dragging = active?.kind === 'field' ? findProperty(value, active.propertyId) : null

  const state = useMemo<BuilderState>(
    () => ({
      draft: value,
      onChange,
      issues: issuesById(issues),
      dragging,
      added,
      addField: (objectId, index, type) => {
        const object = findObject(value, objectId)
        if (object === null) return
        const property = newProperty(freeName(object), type)
        setAdded(property.id)
        onChange(insertProperty(value, objectId, index, property))
      },
    }),
    [value, onChange, issues, dragging, added],
  )

  const onDragStart = ({ active: started }: DragStartEvent) => setActive(readSource(started.id))
  const onDragEnd = ({ active: ended, over }: DragEndEvent) => {
    setActive(null)
    const source = readSource(ended.id)
    const target = over === null ? null : readTarget(over.id)
    if (source === null || target === null) return
    if (source.kind === 'palette') state.addField(target.objectId, target.index, source.type)
    else onChange(moveProperty(value, source.propertyId, target.objectId, target.index))
  }

  return (
    <BuilderContext.Provider value={state}>
      <DndContext
        sensors={sensors}
        collisionDetection={nearestSlot}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        onDragCancel={() => setActive(null)}
        accessibility={{ screenReaderInstructions: { draggable: 'Use the actions menu of each field to move it with the keyboard.' } }}
      >
        <div className="flex flex-col gap-4">
          <Palette onAdd={(type) => state.addField(value.root.id, value.root.properties.length, type)} />
          <div className="flex flex-col gap-3 rounded-xl border bg-background p-3 shadow-card">
            <div className="flex flex-wrap items-center gap-2 px-1">
              <span className="font-medium">Event payload</span>
              <Badge className="font-mono">object</Badge>
              <label className="ml-auto flex items-center gap-2 text-[12px]/[16px] font-medium text-muted-foreground">
                <Switch
                  aria-label="The payload rejects fields that are not listed"
                  checked={value.root.closed}
                  onCheckedChange={(closed) => onChange({ ...value, root: { ...value.root, closed } })}
                />
                Only listed fields
              </label>
            </div>
            <PropertyList object={value.root} path="" blocked={false} />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="w-fit"
              onClick={() => state.addField(value.root.id, value.root.properties.length, 'string')}
            >
              <Plus strokeWidth={1.75} aria-hidden />
              Add field
            </Button>
          </div>
        </div>
        <DragOverlay dropAnimation={null}>{active === null ? null : <DragPreview source={active} draft={value} />}</DragOverlay>
      </DndContext>
    </BuilderContext.Provider>
  )
}

function Palette({ onAdd }: { onAdd: (type: DraftType) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12px]/[16px] text-muted-foreground">Drag a type into the fields, or click it to add a field at the end.</p>
      <ul aria-label="Field types" className="flex flex-wrap gap-2">
        {PALETTE.map((type) => (
          <li key={type}>
            <PaletteItem type={type} onAdd={() => onAdd(type)} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function PaletteItem({ type, onAdd }: { type: DraftType; onAdd: () => void }) {
  const { setNodeRef, listeners, attributes, isDragging } = useDraggable({ id: sourceId({ kind: 'palette', type }) })
  const Icon = typeIcon[type]
  return (
    <button
      type="button"
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      // dnd-kit's attributes make it a `role="button"` with drag instructions; a click adds the field instead.
      role={undefined}
      aria-roledescription={undefined}
      aria-describedby={undefined}
      aria-label={`Add ${draftTypeLabel[type].toLowerCase()} field`}
      onClick={onAdd}
      className={cn(
        'inline-flex h-8 cursor-grab touch-none items-center gap-1.5 rounded-md border bg-card px-2.5 text-[13px]/[20px] font-medium text-card-foreground select-none',
        'hover:border-primary/50 hover:bg-accent active:scale-97 active:cursor-grabbing',
        controlTransition,
        focusRing,
        isDragging && 'opacity-40',
      )}
    >
      <Icon size={14} strokeWidth={1.75} aria-hidden className="text-primary" />
      {draftTypeLabel[type]}
    </button>
  )
}

function DragPreview({ source, draft }: { source: DragSource; draft: SchemaDraft }) {
  const property = source.kind === 'field' ? findProperty(draft, source.propertyId) : null
  const type = source.kind === 'palette' ? source.type : (property?.node.type ?? 'string')
  const Icon = typeIcon[type]
  return (
    <div className="inline-flex h-10 cursor-grabbing items-center gap-2 rounded-lg whitespace-nowrap border border-primary/40 bg-card pr-3 pl-1 text-card-foreground shadow-popover">
      <GripVertical size={16} strokeWidth={1.75} className="text-muted-foreground" aria-hidden />
      <Icon size={16} strokeWidth={1.75} className="text-primary" aria-hidden />
      <span className={cn('font-medium', property !== null && 'font-mono text-[13px]')}>
        {property === null ? `New ${draftTypeLabel[type].toLowerCase()} field` : property.name || 'unnamed field'}
      </span>
      <Badge className="font-mono">{draftTypeLabel[type]}</Badge>
    </div>
  )
}
