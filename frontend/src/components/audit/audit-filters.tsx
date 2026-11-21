import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { getListUsersQueryOptions } from '@/api/generated/users/users'
import type { AuditAction, AuditEntityType, TeamRead, UserRead } from '@/api/generated/model'
import { Button } from '@/components/ui/button'
import { Combobox, ComboboxContent, ComboboxInput, ComboboxItem } from '@/components/ui/combobox'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from '@/components/ui/popover'
import { SegmentedControl, type SegmentedOption } from '@/components/ui/segmented-control'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { usePersonName } from '@/hooks/use-person-name'
import { useVisibleTeams } from '@/hooks/use-visible-teams'
import { unexpectedStatusMessage } from '@/lib/api'
import {
  actionEntityType,
  actionsOf,
  auditActionText,
  auditEntityTypes,
  auditRanges,
  auditSearch,
  entityTypeLabel,
  isFiltered,
  rangeLabel,
  type AuditFilters,
  type AuditRange,
} from '@/lib/audit'
import { OFFLINE } from '@/lib/pagination'

/** Users the actor filter offers; `GET /users` answers at most this many at once. */
const USERS_PAGE_LIMIT = 100

/** Segmented control value for "no range". */
const ALL_TIME = 'all'

const rangeOptions: readonly SegmentedOption<AuditRange | typeof ALL_TIME>[] = [
  ...auditRanges.map((range) => ({ value: range, label: rangeLabel[range] })),
  { value: ALL_TIME, label: 'All time' },
]

/** Combobox values besides user ids: everyone, or only the system. */
const ANYONE = 'anyone'
const SYSTEM = 'system'

/** Props for `AuditFilterBar`. */
export interface AuditFilterBarProps {
  filters: AuditFilters
  /** Called with the new filters on every change; the route writes them to the address. */
  onChange: (filters: AuditFilters) => void
  /** The team a team page lists; the admin page passes none and gets a team filter. */
  team?: TeamRead
}

/**
 * The audit log's filters (`UI-6`): time range, entity type, action, who did it and, on the admin page, the team.
 * Every change applies at once. An entity id filter, set by an entry's history link or **Filter by ID**, shows as a
 * removable chip.
 */
export function AuditFilterBar({ filters, onChange, team }: AuditFilterBarProps) {
  const set = (changes: Partial<AuditFilters>) => onChange({ ...filters, ...changes })

  return (
    <div role="search" aria-label="Filter the audit log" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <EntityTypeFilter
          value={filters.entity_type}
          onChange={(entityType) =>
            set({
              entity_type: entityType,
              action: actionFits(filters.action, entityType) ? filters.action : undefined,
            })
          }
          types={team === undefined ? auditEntityTypes : auditEntityTypes.filter((type) => type !== 'user')}
        />
        <ActionFilter entityType={filters.entity_type} value={filters.action} onChange={(action) => set({ action })} />
        <ActorFilter filters={filters} onChange={set} />
        {team === undefined && <TeamFilter filters={filters} onChange={set} />}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <SegmentedControl
          aria-label="Time range"
          options={rangeOptions}
          value={filters.range ?? ALL_TIME}
          onValueChange={(range) => set({ range: range === ALL_TIME ? undefined : range })}
        />
        {filters.entity_id !== undefined && (
          <EntityChip
            entityType={filters.entity_type}
            entityId={filters.entity_id}
            onRemove={() => set({ entity_id: undefined })}
          />
        )}
        <EntityIdFilter onApply={(entityId) => set({ entity_id: entityId })} />
        {isFiltered(filters) && (
          <Button variant="ghost" size="sm" onClick={() => onChange({})}>
            Clear filters
          </Button>
        )}
      </div>
    </div>
  )
}

/** Whether `action` can match entries of `entityType`; any action fits when no type is chosen. */
function actionFits(action: AuditAction | undefined, entityType: AuditEntityType | undefined): boolean {
  return action === undefined || entityType === undefined || actionEntityType[action] === entityType
}

function EntityTypeFilter({
  value,
  onChange,
  types,
}: {
  value: AuditEntityType | undefined
  onChange: (entityType: AuditEntityType | undefined) => void
  types: readonly AuditEntityType[]
}) {
  const items = [
    { value: null, label: 'All types' },
    ...types.map((type) => ({ value: type, label: entityTypeLabel(type) })),
  ]
  return (
    <Field className="w-full sm:w-44">
      <FieldLabel>Entity type</FieldLabel>
      <Select items={items} value={value ?? null} onValueChange={(next) => onChange(next ?? undefined)}>
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.value ?? ''} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}

/** Actions grouped by the entity type they name; only that type's actions once a type is chosen. */
function ActionFilter({
  entityType,
  value,
  onChange,
}: {
  entityType: AuditEntityType | undefined
  value: AuditAction | undefined
  onChange: (action: AuditAction | undefined) => void
}) {
  const groups = (entityType === undefined ? auditEntityTypes : [entityType]).map((type) => ({
    type,
    actions: actionsOf(type),
  }))
  const items = [
    { value: null, label: 'All actions' },
    ...groups.flatMap(({ actions }) => actions.map((action) => ({ value: action, label: auditActionText(action) }))),
  ]
  return (
    <Field className="w-full sm:w-64">
      <FieldLabel>Action</FieldLabel>
      <Select items={items} value={value ?? null} onValueChange={(next) => onChange(next ?? undefined)}>
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="max-h-80">
          <SelectItem value={null}>All actions</SelectItem>
          {groups.map(({ type, actions }) => (
            <SelectGroup key={type}>
              <SelectLabel>{entityTypeLabel(type)}</SelectLabel>
              {actions.map((action) => (
                <SelectItem key={action} value={action}>
                  {auditActionText(action)}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}

/** Anyone, the system, or one user, searched by name or email; `GET /users` loads on first open. */
/** Props of the filters that set two address params at once. */
interface PairFilterProps {
  filters: AuditFilters
  onChange: (changes: Partial<AuditFilters>) => void
}

function ActorFilter({ filters, onChange }: PairFilterProps) {
  const [opened, setOpened] = useState(false)
  const personName = usePersonName()
  const users = useQuery({ ...getListUsersQueryOptions({ limit: USERS_PAGE_LIMIT }), enabled: opened })

  let listed: UserRead[] = []
  let empty = 'No one matches.'
  if (opened && users.isPending) empty = 'Loading people…'
  else if (users.isError) empty = OFFLINE
  else if (users.data !== undefined) {
    const response = users.data
    switch (response.status) {
      case 200:
        listed = response.data
        break
      case 401:
        break
      case 422:
        empty = "Couldn't load people. Reload the page and try again."
        break
      default:
        empty = unexpectedStatusMessage(response)
    }
  }
  const byId = new Map(listed.map((user) => [user.id, user]))
  const value = filters.actor_user_id ?? (filters.system === true ? SYSTEM : null)
  const ids = listed.map((user) => user.id)
  if (filters.actor_user_id !== undefined && !byId.has(filters.actor_user_id)) ids.unshift(filters.actor_user_id)

  const label = (option: string): string => {
    if (option === ANYONE) return 'Anyone'
    if (option === SYSTEM) return 'System'
    const user = byId.get(option)
    if (user !== undefined) return user.display_name
    const person = personName(option)
    switch (person.kind) {
      case 'me':
        return 'You'
      case 'name':
        return person.name
      case 'id':
        return `User ${person.shortId}`
    }
  }

  return (
    <Field className="w-full sm:w-56">
      <FieldLabel>Who</FieldLabel>
      <Combobox
        items={[ANYONE, SYSTEM, ...ids]}
        value={value}
        onValueChange={(next) => {
          if (next === null || next === ANYONE) onChange({ actor_user_id: undefined, system: undefined })
          else if (next === SYSTEM) onChange({ actor_user_id: undefined, system: true })
          else onChange({ actor_user_id: next, system: undefined })
        }}
        onOpenChange={(open) => open && setOpened(true)}
        itemToStringLabel={label}
        filter={(option, query) => {
          const needle = query.trim().toLowerCase()
          const user = byId.get(option)
          return (
            label(option).toLowerCase().includes(needle) ||
            (user !== undefined && user.email.toLowerCase().includes(needle))
          )
        }}
      >
        <ComboboxInput placeholder="Anyone" />
        <ComboboxContent empty={empty}>
          {(option: string) => {
            const user = byId.get(option)
            return (
              <ComboboxItem key={option} value={option}>
                <span className="truncate">{label(option)}</span>
                {user !== undefined && (
                  <span className="truncate text-[12px]/[16px] text-muted-foreground">{user.email}</span>
                )}
              </ComboboxItem>
            )
          }}
        </ComboboxContent>
      </Combobox>
    </Field>
  )
}

/** Every team, one team, or entries without a team; admin page only. */
function TeamFilter({ filters, onChange }: PairFilterProps) {
  const { teams } = useVisibleTeams()
  const NO_TEAM = 'none'
  const items = [
    { value: null, label: 'All teams' },
    { value: NO_TEAM, label: 'No team' },
    ...teams.map(({ team }) => ({ value: team.id, label: team.name })),
  ]
  const value = filters.team_id ?? (filters.without_team === true ? NO_TEAM : null)
  return (
    <Field className="w-full sm:w-48">
      <FieldLabel>Team</FieldLabel>
      <Select
        items={items}
        value={value}
        onValueChange={(next) => {
          if (next === null) onChange({ team_id: undefined, without_team: undefined })
          else if (next === NO_TEAM) onChange({ team_id: undefined, without_team: true })
          else onChange({ team_id: next, without_team: undefined })
        }}
      >
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="max-h-80">
          {items.map((item) => (
            <SelectItem key={item.value ?? ''} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
}

/** The entity the log is filtered to: its type in words and short id, with a button that removes the filter. */
function EntityChip({
  entityType,
  entityId,
  onRemove,
}: {
  entityType: AuditEntityType | undefined
  entityId: string
  onRemove: () => void
}) {
  const label = entityType === undefined ? 'Entity' : entityTypeLabel(entityType)
  return (
    <span
      className="inline-flex h-7 items-center gap-1 rounded-full bg-muted pr-0.5 pl-2.5 text-[12px]/[16px] font-medium"
    >
      {label}
      <span className="font-mono text-muted-foreground" title={entityId}>
        {entityId.slice(0, 8)}
      </span>
      <Button
        variant="ghost"
        size="icon-sm"
        className="size-6 rounded-full"
        aria-label={`Stop filtering by ${label.toLowerCase()} ${entityId}`}
        onClick={onRemove}
      >
        <X strokeWidth={1.75} />
      </Button>
    </span>
  )
}

/** **Filter by ID**: a popover with an entity id field; an id that is not a full UUID stays there with an error. */
function EntityIdFilter({ onApply }: { onApply: (entityId: string) => void }) {
  const [open, setOpen] = useState(false)
  const [entityId, setEntityId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const parsed = auditSearch.shape.entity_id.parse(entityId.trim())
    if (parsed === undefined) {
      setError('Enter the full entity ID, 36 characters with dashes.')
      return
    }
    onApply(parsed)
    setOpen(false)
    setEntityId('')
    setError(null)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={<Button variant="ghost" size="sm" />}>Filter by ID</PopoverTrigger>
      <PopoverContent align="start" className="w-96">
        <PopoverTitle>Filter by ID</PopoverTitle>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field invalid={error !== null}>
            <FieldLabel>Entity ID</FieldLabel>
            <Input
              value={entityId}
              onValueChange={(next) => {
                setEntityId(next)
                setError(null)
              }}
              className="font-mono text-[13px]/[20px]"
              autoComplete="off"
              spellCheck={false}
            />
            {error !== null && <FieldError>{error}</FieldError>}
          </Field>
          <Button type="submit" variant="secondary" className="self-end">
            Apply filter
          </Button>
        </form>
      </PopoverContent>
    </Popover>
  )
}
