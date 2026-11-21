import { useMemo, type Ref } from 'react'
import { Combobox } from '@base-ui/react/combobox'
import { CheckIcon, ChevronDownIcon } from 'lucide-react'
import { layers } from '@/lib/layers'
import { timeZoneOptions, utcOffsetLabel } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import { controlTransition, fieldControl, focusRing, layerMotion, layerSurface, listItem } from '@/components/ui/styles'

/** Props for `TimeZoneSelect`. */
export interface TimeZoneSelectProps {
  /** Selected IANA time zone, e.g. `Europe/Prague`; always one of the options. */
  value: string
  onValueChange: (zone: string) => void
  onBlur?: () => void
  disabled?: boolean
  /** Ref to the text input, so a form can focus it on an error. */
  inputRef?: Ref<HTMLInputElement>
  className?: string
}

/**
 * Searchable list of IANA time zones (DOMAIN.md §1) with each zone's current UTC offset. Typing filters the list;
 * the saved zone is always an option, even when the browser doesn't list it. Inside a `Field` the label targets
 * the input.
 */
export function TimeZoneSelect({ value, onValueChange, onBlur, disabled, inputRef, className }: TimeZoneSelectProps) {
  const zones = useMemo(() => timeZoneOptions(value), [value])
  return (
    <Combobox.Root<string>
      items={zones}
      value={value}
      onValueChange={(zone) => {
        if (zone !== null) onValueChange(zone)
      }}
      disabled={disabled}
      autoHighlight
    >
      <Combobox.InputGroup className={cn('relative w-full', className)}>
        <Combobox.Input
          ref={inputRef}
          onBlur={onBlur}
          className={cn(fieldControl, controlTransition, focusRing, 'py-1 pr-8')}
        />
        {/* A decorative chevron: the input opens the list on click and Arrow Down, and a Trigger button would take the field's label too. */}
        <Combobox.Icon className="pointer-events-none absolute inset-y-0 right-0 flex w-8 items-center justify-center text-muted-foreground">
          <ChevronDownIcon className="size-4" strokeWidth={1.75} />
        </Combobox.Icon>
      </Combobox.InputGroup>
      <Combobox.Portal className="relative isolate" style={{ zIndex: layers.popover }}>
        <Combobox.Positioner sideOffset={6} align="start">
          <Combobox.Popup
            className={cn(
              'w-(--anchor-width) max-w-(--available-width) overflow-hidden p-1 outline-none',
              layerSurface,
              layerMotion,
            )}
          >
            <Combobox.Empty className="px-2 py-1.5 text-[12px]/[16px] text-muted-foreground empty:hidden">
              No time zone matches. Try a city, such as Prague.
            </Combobox.Empty>
            <Combobox.List className="max-h-[min(20rem,var(--available-height))] overflow-y-auto overscroll-contain outline-none">
              {(zone: string) => (
                <Combobox.Item key={zone} value={zone} className={cn(listItem, 'pr-8')}>
                  <span className="flex-1 truncate">{zone}</span>
                  <span className="font-mono text-[12px]/[16px] text-muted-foreground tabular-nums">
                    {utcOffsetLabel(zone)}
                  </span>
                  <Combobox.ItemIndicator className="absolute right-2 flex items-center">
                    <CheckIcon strokeWidth={1.75} />
                  </Combobox.ItemIndicator>
                </Combobox.Item>
              )}
            </Combobox.List>
          </Combobox.Popup>
        </Combobox.Positioner>
      </Combobox.Portal>
    </Combobox.Root>
  )
}
