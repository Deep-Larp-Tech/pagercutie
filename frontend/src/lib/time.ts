const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

/** Units `relativeTime` picks from, largest first, with their length in seconds. */
const units = [
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
] as const satisfies readonly (readonly [Intl.RelativeTimeFormatUnit, number])[]

/** `iso` relative to `now` in plain words: "now", "3 minutes ago", "yesterday". */
export function relativeTime(iso: string, now: number): string {
  const seconds = Math.round((Date.parse(iso) - now) / 1000)
  for (const [unit, length] of units) {
    if (Math.abs(seconds) >= length) return relative.format(Math.trunc(seconds / length), unit)
  }
  return relative.format(0, 'second')
}

/** A British-English formatter in `timeZone`, or in the browser's zone when `timeZone` is not a valid IANA name. */
function formatter(options: Intl.DateTimeFormatOptions, timeZone: string | undefined): Intl.DateTimeFormat {
  try {
    return new Intl.DateTimeFormat('en-GB', { ...options, timeZone })
  } catch {
    return new Intl.DateTimeFormat('en-GB', options)
  }
}

/** `iso` as a date and time in `timeZone` (the browser's when omitted): "23 Nov 2026, 09:00". */
export function absoluteTime(iso: string, timeZone?: string): string {
  return formatter({ dateStyle: 'medium', timeStyle: 'short' }, timeZone).format(new Date(iso))
}

/** `iso` as a weekday and 24-hour time in `timeZone`, for the end of an on-call shift: "Mon 09:00". */
export function weekdayTime(iso: string, timeZone?: string): string {
  return formatter({ weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }, timeZone).format(
    new Date(iso),
  )
}
