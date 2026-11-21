import { createUserBodyTimezoneDefault } from '@/api/generated/users/users.zod'

/** The browser's IANA time zone, or the contract default (`UTC`) when the browser reports none. */
export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || createUserBodyTimezoneDefault
  } catch {
    return createUserBodyTimezoneDefault
  }
}

/**
 * IANA time zones to pick from, sorted: the browser's list plus the contract default and `current`, which the list
 * may omit (`UTC` or an alias such as `Europe/Kiev` stored earlier).
 */
export function timeZoneOptions(current?: string): string[] {
  const zones = new Set(Intl.supportedValuesOf('timeZone'))
  zones.add(createUserBodyTimezoneDefault)
  if (current !== undefined) zones.add(current)
  return [...zones].toSorted((a, b) => a.localeCompare(b))
}
