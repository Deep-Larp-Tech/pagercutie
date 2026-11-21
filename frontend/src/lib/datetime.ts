/** Locale for times and numbers in the UI: 24-hour clock and day-month order, as in DESIGN.md ("14:02", "Mon 09:00"). */
const LOCALE = 'en-GB'

/** Whether `zone` is an IANA time zone this browser can format times in. */
export function isKnownTimeZone(zone: string): boolean {
  try {
    new Intl.DateTimeFormat(LOCALE, { timeZone: zone })
    return true
  } catch {
    return false
  }
}

/** `zone` when the browser knows it, otherwise `undefined` (the browser's own zone). */
export function usableTimeZone(zone: string): string | undefined {
  return isKnownTimeZone(zone) ? zone : undefined
}

let supportedZones: readonly string[] | undefined

/**
 * IANA time zones to pick from, sorted: the browser's list plus `UTC` (the backend's default, which
 * `Intl.supportedValuesOf` leaves out) and `current`, so the saved value is always an option.
 */
export function timeZoneOptions(current: string): string[] {
  supportedZones ??= Intl.supportedValuesOf('timeZone')
  const zones = new Set([...supportedZones, 'UTC'])
  if (current !== '') zones.add(current)
  return [...zones].sort((a, b) => a.localeCompare(b))
}

const offsetByZone = new Map<string, string>()

/** Current UTC offset of `zone`, e.g. `GMT+1`; empty for a zone the browser doesn't know. */
export function utcOffsetLabel(zone: string): string {
  const cached = offsetByZone.get(zone)
  if (cached !== undefined) return cached
  let label = ''
  if (isKnownTimeZone(zone)) {
    const parts = new Intl.DateTimeFormat(LOCALE, { timeZone: zone, timeZoneName: 'shortOffset' }).formatToParts()
    label = parts.find((part) => part.type === 'timeZoneName')?.value ?? ''
  }
  offsetByZone.set(zone, label)
  return label
}

function calendarPart(date: Date, timeZone: string | undefined, part: 'day' | 'year'): string {
  const options: Intl.DateTimeFormatOptions =
    part === 'day' ? { year: 'numeric', month: '2-digit', day: '2-digit' } : { year: 'numeric' }
  return new Intl.DateTimeFormat(LOCALE, { timeZone, ...options }).format(date)
}

/**
 * Short time of `iso` in `timeZone`: `14:02` today, `20 Nov, 14:02` on another day this year, `20 Nov 2025, 14:02`
 * before that. A zone the browser doesn't know falls back to the browser's own.
 */
export function formatShortTime(iso: string, timeZone: string, now: Date = new Date()): string {
  const zone = usableTimeZone(timeZone)
  const date = new Date(iso)
  const time = new Intl.DateTimeFormat(LOCALE, { timeZone: zone, hour: '2-digit', minute: '2-digit' }).format(date)
  if (calendarPart(date, zone, 'day') === calendarPart(now, zone, 'day')) return time
  const sameYear = calendarPart(date, zone, 'year') === calendarPart(now, zone, 'year')
  const day = new Intl.DateTimeFormat(LOCALE, {
    timeZone: zone,
    day: 'numeric',
    month: 'short',
    year: sameYear ? undefined : 'numeric',
  }).format(date)
  return `${day}, ${time}`
}

/** Full date and time of `iso` in `timeZone` for tooltips, e.g. `Saturday, 21 November 2026 at 14:02:05 CET`. */
export function formatFullTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat(LOCALE, {
    timeZone: usableTimeZone(timeZone),
    dateStyle: 'full',
    timeStyle: 'long',
  }).format(new Date(iso))
}
