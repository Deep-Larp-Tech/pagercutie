import { createContext, useContext } from 'react'
import type { UniqueIdentifier } from '@dnd-kit/core'
import { Binary, Braces, Brackets, CircleSlash, Hash, Quote, ToggleLeft, Type, type LucideIcon } from 'lucide-react'
import { DRAFT_TYPES, type DraftType, type IssuePart, type PropertyDraft, type SchemaDraft } from '@/lib/schema-draft'

/** Icon of each builder type in the palette, the rows and the drag preview. */
export const typeIcon = {
  string: Type,
  number: Hash,
  integer: Binary,
  boolean: ToggleLeft,
  null: CircleSlash,
  object: Braces,
  array: Brackets,
  literal: Quote,
} as const satisfies Record<DraftType, LucideIcon>

/** What is being dragged: a type from the palette, or an existing field by its handle. */
export type DragSource = { kind: 'palette'; type: DraftType } | { kind: 'field'; propertyId: string }

/** Where a drop lands: index `index` of the object `objectId`, counted before the move. */
export interface DropTarget {
  objectId: string
  index: number
}

/** dnd-kit id of a drag source. */
export function sourceId(source: DragSource): string {
  return source.kind === 'palette' ? `palette:${source.type}` : `field:${source.propertyId}`
}

/** The drag source a dnd-kit id names, or `null` for an id this builder did not make. */
export function readSource(id: UniqueIdentifier): DragSource | null {
  const [kind, rest] = String(id).split(/:(.*)/s)
  if (kind === 'field' && rest !== undefined) return { kind: 'field', propertyId: rest }
  const type = DRAFT_TYPES.find((candidate) => candidate === rest)
  return kind === 'palette' && type !== undefined ? { kind: 'palette', type } : null
}

/** dnd-kit id of a drop slot. */
export function targetId({ objectId, index }: DropTarget): string {
  return `slot:${objectId}:${index}`
}

/** The drop slot a dnd-kit id names, or `null`. */
export function readTarget(id: UniqueIdentifier): DropTarget | null {
  const match = /^slot:(.+):(\d+)$/.exec(String(id))
  return match === null ? null : { objectId: match[1], index: Number(match[2]) }
}

/** State the builder's rows share. */
export interface BuilderState {
  draft: SchemaDraft
  onChange: (draft: SchemaDraft) => void
  /** Problems per node or property id, then per part. */
  issues: Partial<Record<string, Partial<Record<IssuePart, string>>>>
  /** The field being dragged; drop slots inside it are turned off. */
  dragging: PropertyDraft | null
  /** Id of the field added last; its name input takes focus when it mounts. */
  added: string | null
  /** Adds a field of `type` with a free name at `index` of the object `objectId`. */
  addField: (objectId: string, index: number, type: DraftType) => void
}

export const BuilderContext = createContext<BuilderState | null>(null)

/** The builder state for a row; only valid under `SchemaBuilder`. */
export function useBuilder(): BuilderState {
  const state = useContext(BuilderContext)
  if (state === null) throw new Error('useBuilder must be used under SchemaBuilder.')
  return state
}

/** Dotted path of a field from the payload root, as `FieldTree` writes it (`error.code`, `lines[].amount`). */
export function joinPath(parent: string, name: string): string {
  if (name === '[]') return `${parent}[]`
  return parent === '' ? name : `${parent}.${name}`
}
