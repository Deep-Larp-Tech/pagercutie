import type { Channel, ChannelRule, TimeWindow, Weekday } from '@/api/generated/model'
import { toHourMinute, WEEK, weekdayLabel } from './local-time'
import { severityLabel } from './severity'

/** Largest number of rules one set of channel preferences may hold (`ChannelPreferences.rules`, max 20). */
export const MAX_CHANNEL_RULES = 20

/** What happens to an alert no rule matches (DOMAIN.md §5). */
export const FALLBACK_SUMMARY = 'Anything else: UI only'

/** User-facing channel name. */
export const channelLabel = {
  email: 'Email',
  sms: 'SMS',
  phone: 'Phone call',
  ui: 'UI',
} as const satisfies Record<Channel, string>

const WORKWEEK: readonly Weekday[] = ['mon', 'tue', 'wed', 'thu', 'fri']
const WEEKEND: readonly Weekday[] = ['sat', 'sun']

function sameDays(days: ReadonlySet<Weekday>, expected: readonly Weekday[]): boolean {
  return days.size === expected.length && expected.every((day) => days.has(day))
}

/** Days of a window in words: "every day", "weekdays", "weekends" or "Mon, Wed, Fri" (Monday first). */
export function describeDays(days: readonly Weekday[] | undefined): string {
  // The API fills in every day when `days` is omitted (`TimeWindow.days`).
  const set = new Set(days ?? WEEK)
  if (set.size === WEEK.length) return 'every day'
  if (sameDays(set, WORKWEEK)) return 'weekdays'
  if (sameDays(set, WEEKEND)) return 'weekends'
  return WEEK.filter((day) => set.has(day))
    .map((day) => weekdayLabel[day])
    .join(', ')
}

/** A window in words, e.g. "weekdays 08:00 to 20:00"; a window ending before it starts runs into the next day. */
export function describeWindow(window: TimeWindow): string {
  const start = toHourMinute(window.start)
  const end = toHourMinute(window.end)
  const nextDay = end < start ? ' the next day' : ''
  return `${describeDays(window.days)} ${start} to ${end}${nextDay}`
}

/**
 * One preference rule in plain words, e.g. "Critical and above: SMS, weekdays 08:00 to 20:00". `debug` reads
 * "Any severity", since every alert is at or above it.
 */
export function describeRule(rule: ChannelRule): string {
  const severity = rule.min_severity === 'debug' ? 'Any severity' : `${severityLabel[rule.min_severity]} and above`
  const channels = rule.channels.map((channel) => channelLabel[channel]).join(', ')
  const when = rule.window ? describeWindow(rule.window) : 'at any time'
  return `${severity}: ${channels || 'no channel'}, ${when}`
}
