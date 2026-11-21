import type { Colour, Severity } from '@/api/generated/model'
import { Badge } from '@/components/ui/badge'
import { alertColourClass, defaultColour, severityIcon, severityLabel } from '@/lib/severity'
import { cn } from '@/lib/utils'

/** Props for `SeverityBadge`. */
export interface SeverityBadgeProps {
  severity: Severity
  /** The rule's colour; defaults to the severity's colour (DESIGN.md §4.3). */
  colour?: Colour
  className?: string
}

/** Severity as an icon and a label on the rule colour's tint, so it reads without colour (DESIGN.md §4.3). */
export function SeverityBadge({ severity, colour = defaultColour[severity], className }: SeverityBadgeProps) {
  const Icon = severityIcon[severity]
  return (
    <Badge variant="tint" className={cn(alertColourClass[colour], className)}>
      <Icon strokeWidth={1.75} aria-hidden />
      {severityLabel[severity]}
    </Badge>
  )
}
