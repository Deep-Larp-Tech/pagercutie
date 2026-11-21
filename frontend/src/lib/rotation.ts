import type { Rotation, Weekday } from '@/api/generated/model'

/** A rotation with every field set, as the rotation form holds it; `handoff_time` is `HH:MM`. */
export type RotationPlan = Required<Rotation>

/** One on-call shift: `userId` is on call from `start` until `end`. */
export interface Shift {
  userId: string
  start: Date
  end: Date
}

/** Who `GET /teams/{id}/on-call` says is on call now and when their shift ends. */
export interface OnCallAnchor {
  userId: string
  until: Date
}

/** `Date.getUTCDay()` number of each weekday (Sunday is 0). */
const DAY_NUMBER = {
  sun: 0,
  mon: 1,
  tue: 2,
  wed: 3,
  thu: 4,
  fri: 5,
  sat: 6,
} as const satisfies Record<Weekday, number>

interface LocalTime {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  second: number
}

const formatters = new Map<string, Intl.DateTimeFormat>()

function formatter(timeZone: string): Intl.DateTimeFormat {
  let format = formatters.get(timeZone)
  if (format === undefined) {
    format = new Intl.DateTimeFormat('en-US', {
      timeZone,
      hourCycle: 'h23',
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
      second: 'numeric',
    })
    formatters.set(timeZone, format)
  }
  return format
}

function localTime(instant: number, timeZone: string): LocalTime {
  const parts = formatter(timeZone).formatToParts(instant)
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((candidate) => candidate.type === type)?.value ?? 0)
  return {
    year: part('year'),
    month: part('month'),
    day: part('day'),
    hour: part('hour'),
    minute: part('minute'),
    second: part('second'),
  }
}

/** Milliseconds `timeZone` is ahead of UTC at `instant`. */
function offset(instant: number, timeZone: string): number {
  const local = localTime(instant, timeZone)
  const asUtc = Date.UTC(local.year, local.month - 1, local.day, local.hour, local.minute, local.second)
  return asUtc - Math.floor(instant / 1000) * 1000
}

/**
 * The instant of a wall-clock time in `timeZone`. Day overflow is allowed (`day: 32`). A time skipped by a DST jump
 * resolves to the instant one offset change later.
 */
function zonedInstant(year: number, month: number, day: number, hour: number, minute: number, timeZone: string): number {
  const guess = Date.UTC(year, month - 1, day, hour, minute)
  const first = guess - offset(guess, timeZone)
  const second = guess - offset(first, timeZone)
  return first === second ? first : second
}

/** Whether `timeZone` is an IANA zone this browser knows. */
export function isTimeZone(timeZone: string): boolean {
  try {
    formatter(timeZone)
    return true
  } catch {
    return false
  }
}

/** The first handoff (weekday and `HH:MM` in the rotation's time zone) strictly after `after`. */
export function nextHandoff(after: Date, plan: Pick<RotationPlan, 'handoff_day' | 'handoff_time' | 'timezone'>): Date {
  const [hour, minute] = plan.handoff_time.split(':').map(Number)
  const local = localTime(after.getTime(), plan.timezone)
  const today = new Date(Date.UTC(local.year, local.month - 1, local.day)).getUTCDay()
  const daysAhead = (DAY_NUMBER[plan.handoff_day] - today + 7) % 7
  let candidate = zonedInstant(local.year, local.month, local.day + daysAhead, hour, minute, plan.timezone)
  if (candidate <= after.getTime()) {
    candidate = zonedInstant(local.year, local.month, local.day + daysAhead + 7, hour, minute, plan.timezone)
  }
  return new Date(candidate)
}

/**
 * The next `count` shifts of a rotation, starting at `now` (DOMAIN.md §5, `DEL-3`).
 *
 * With `anchor` (the saved rotation and its current on-call user), the anchored user is on call until
 * `anchor.until` and the list continues after them. Without it, the rotation is read as if saved at `now`: a `PUT`
 * restarts it with `user_ids[0]` (ADR-0056), who is on call until the next handoff. Each handoff is the next local
 * weekday and time in the rotation's zone, so a DST change shifts the UTC time, not the wall-clock time.
 */
export function upcomingShifts(plan: RotationPlan, now: Date, count: number, anchor?: OnCallAnchor): Shift[] {
  const { user_ids: userIds } = plan
  if (userIds.length === 0 || count <= 0) return []
  const anchorIndex = anchor === undefined ? -1 : userIds.indexOf(anchor.userId)
  const anchored = anchor !== undefined && anchorIndex >= 0 && anchor.until > now
  let index = anchored ? anchorIndex : 0
  let start = now
  let end = anchored ? anchor.until : nextHandoff(now, plan)
  const shifts: Shift[] = []
  for (let n = 0; n < count; n += 1) {
    shifts.push({ userId: userIds[index], start, end })
    index = (index + 1) % userIds.length
    start = end
    end = nextHandoff(start, plan)
  }
  return shifts
}

/** A shift boundary as the rotation's members read it, e.g. `Mon 24 Nov, 09:00`, in the rotation's time zone. */
export function formatShiftTime(instant: Date, timeZone: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(instant)
}
