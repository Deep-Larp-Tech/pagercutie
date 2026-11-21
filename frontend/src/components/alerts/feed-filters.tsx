import { useId } from 'react'
import { AlertStatus, Severity } from '@/api/generated/model'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { AlertFilters } from '@/lib/alert-feed'
import { severityLabel } from '@/lib/severity'

const statusLabel = {
  open: 'Open',
  acknowledged: 'Acknowledged',
  resolved: 'Resolved',
} as const satisfies Record<AlertStatus, string>

/** Most severe first, the order people scan for. */
const severities = [
  Severity.critical,
  Severity.error,
  Severity.warn,
  Severity.info,
  Severity.debug,
] as const satisfies readonly Severity[]

/** Props for `FeedFilters`. */
export interface FeedFiltersProps {
  value: AlertFilters
  onChange: (filters: AlertFilters) => void
}

/** Status and severity toggles above a feed; with none pressed in a group, the feed shows every value of it. */
export function FeedFilters({ value, onChange }: FeedFiltersProps) {
  const id = useId()
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
      <div className="flex items-center gap-2">
        <span id={`${id}-status`} className="text-[12px]/[16px] font-medium text-muted-foreground">
          Status
        </span>
        <ToggleGroup<AlertStatus>
          multiple
          aria-labelledby={`${id}-status`}
          value={value.status ?? []}
          onValueChange={(status) => onChange({ ...value, status })}
        >
          {Object.values(AlertStatus).map((status) => (
            <ToggleGroupItem key={status} value={status}>
              {statusLabel[status]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      <div className="flex items-center gap-2">
        <span id={`${id}-severity`} className="text-[12px]/[16px] font-medium text-muted-foreground">
          Severity
        </span>
        <ToggleGroup<Severity>
          multiple
          aria-labelledby={`${id}-severity`}
          value={value.severity ?? []}
          onValueChange={(severity) => onChange({ ...value, severity })}
        >
          {severities.map((severity) => (
            <ToggleGroupItem key={severity} value={severity}>
              {severityLabel[severity]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
    </div>
  )
}
