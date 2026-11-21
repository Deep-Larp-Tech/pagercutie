import type { KeyboardEvent } from 'react'
import { Autocomplete } from '@base-ui/react/autocomplete'
import { ChevronDownIcon } from 'lucide-react'
import { controlTransition, fieldControl, focusRing, layerMotion, layerSurface, listItem } from '@/components/ui/styles'
import type { EventField, FieldType } from '@/lib/event-fields'
import { layers } from '@/lib/layers'
import { cn } from '@/lib/utils'

/** Short name of each field type in the suggestion list. */
const fieldTypeLabel = {
  string: 'text',
  number: 'number',
  boolean: 'yes / no',
  array: 'list',
  object: 'group',
  severity: 'severity',
  unknown: 'any',
} as const satisfies Record<FieldType, string>

/** Props for `FieldPathInput`. */
export interface FieldPathInputProps {
  /** The typed path, e.g. `payload.error.code`. */
  value: string
  onValueChange: (path: string) => void
  /** Suggestions: the selected event schemas' fields and the event metadata. */
  fields: readonly EventField[]
  'aria-label'?: string
  id?: string
  invalid?: boolean
  disabled?: boolean
  placeholder?: string
  className?: string
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void
}

/**
 * A field path typed freely with suggestions from the event schemas (`RUL-1`: any field, including ones no schema
 * describes). Built on Base UI Autocomplete, so the text is never forced onto a suggestion.
 */
export function FieldPathInput({
  value,
  onValueChange,
  fields,
  'aria-label': ariaLabel,
  id,
  invalid = false,
  disabled,
  placeholder = 'e.g. payload.error.code',
  className,
  onKeyDown,
}: FieldPathInputProps) {
  return (
    <Autocomplete.Root<EventField>
      items={fields}
      value={value}
      onValueChange={(next) => onValueChange(next)}
      itemToStringValue={(field) => field.path}
      disabled={disabled}
    >
      <Autocomplete.InputGroup className={cn('relative w-full', className)}>
        <Autocomplete.Input
          id={id}
          aria-label={ariaLabel}
          aria-invalid={invalid || undefined}
          placeholder={placeholder}
          spellCheck={false}
          onKeyDown={onKeyDown}
          className={cn(fieldControl, controlTransition, focusRing, 'py-1 pr-8 font-mono text-[13px]')}
        />
        <Autocomplete.Icon className="pointer-events-none absolute inset-y-0 right-0 flex w-8 items-center justify-center text-muted-foreground">
          <ChevronDownIcon className="size-4" strokeWidth={1.75} />
        </Autocomplete.Icon>
      </Autocomplete.InputGroup>
      <Autocomplete.Portal className="relative isolate" style={{ zIndex: layers.popover }}>
        <Autocomplete.Positioner sideOffset={6} align="start">
          <Autocomplete.Popup
            className={cn('w-(--anchor-width) min-w-64 max-w-(--available-width) p-1', layerSurface, layerMotion)}
          >
            <Autocomplete.Empty className="px-2 py-1.5 text-[12px]/[16px] text-muted-foreground empty:hidden">
              No known field matches. You can still use the path you typed.
            </Autocomplete.Empty>
            <Autocomplete.List className="max-h-[min(20rem,var(--available-height))] overflow-y-auto outline-none">
              {(field: EventField) => (
                <Autocomplete.Item key={field.path} value={field} className={listItem}>
                  <span className="flex-1 truncate font-mono text-[13px]">{field.path}</span>
                  <span className="text-[12px]/[16px] text-muted-foreground">{fieldTypeLabel[field.type]}</span>
                </Autocomplete.Item>
              )}
            </Autocomplete.List>
          </Autocomplete.Popup>
        </Autocomplete.Positioner>
      </Autocomplete.Portal>
    </Autocomplete.Root>
  )
}
