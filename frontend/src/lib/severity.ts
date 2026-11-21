import { Bug, CircleX, Info, OctagonAlert, TriangleAlert, type LucideIcon } from 'lucide-react'
import { Colour, type Severity } from '@/api/generated/model'

/** Colour the rule editor pre-fills for each severity (DESIGN.md §4.3, ADR-0033). */
export const defaultColour = {
  critical: Colour.red,
  error: Colour.orange,
  warn: Colour.yellow,
  info: Colour.blue,
  debug: Colour.grey,
} as const satisfies Record<Severity, Colour>

/** Utility class that sets `--c`, `--c-tint` and `--c-text` for a rule colour. */
export const alertColourClass = {
  red: 'alert-red',
  orange: 'alert-orange',
  yellow: 'alert-yellow',
  green: 'alert-green',
  blue: 'alert-blue',
  grey: 'alert-grey',
} as const satisfies Record<Colour, string>

/** Lucide icon shown next to every severity label, so severity reads without colour (UI-6). */
export const severityIcon = {
  critical: OctagonAlert,
  error: CircleX,
  warn: TriangleAlert,
  info: Info,
  debug: Bug,
} as const satisfies Record<Severity, LucideIcon>

/** User-facing severity label in sentence case. */
export const severityLabel = {
  critical: 'Critical',
  error: 'Error',
  warn: 'Warning',
  info: 'Info',
  debug: 'Debug',
} as const satisfies Record<Severity, string>

