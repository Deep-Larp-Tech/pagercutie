import { Weekday } from '@/api/generated/model'

/** Short weekday name, as on a calendar. */
export const weekdayLabel = {
  mon: 'Mon',
  tue: 'Tue',
  wed: 'Wed',
  thu: 'Thu',
  fri: 'Fri',
  sat: 'Sat',
  sun: 'Sun',
} as const satisfies Record<Weekday, string>

/** Full weekday name, for "every Monday". */
export const weekdayName = {
  mon: 'Monday',
  tue: 'Tuesday',
  wed: 'Wednesday',
  thu: 'Thursday',
  fri: 'Friday',
  sat: 'Saturday',
  sun: 'Sunday',
} as const satisfies Record<Weekday, string>

/** Weekdays from Monday to Sunday. */
export const WEEK: readonly Weekday[] = Object.values(Weekday)

/** A wall-clock time as the forms take it: `HH:MM`, 24-hour. */
export const HOUR_MINUTE = /^([01]\d|2[0-3]):[0-5]\d$/

/** `HH:MM` from an API time (`09:00` or `09:00:00`); anything else is returned unchanged. */
export function toHourMinute(time: string): string {
  return /^\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(time) ? time.slice(0, 5) : time
}
