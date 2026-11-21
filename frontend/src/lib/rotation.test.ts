import { describe, expect, test } from 'vitest'
import { nextHandoff, upcomingShifts, type RotationPlan } from './rotation'

const plan: RotationPlan = {
  user_ids: ['petra', 'bob', 'carol'],
  handoff_day: 'mon',
  handoff_time: '09:00',
  timezone: 'Europe/Prague',
}

const iso = (date: Date) => date.toISOString()

describe('nextHandoff', () => {
  test('finds the next handoff weekday and local time in the rotation zone', () => {
    expect(iso(nextHandoff(new Date('2026-11-21T12:00:00Z'), plan))).toBe('2026-11-23T08:00:00.000Z')
  })

  test('a handoff later the same day is the next one', () => {
    expect(iso(nextHandoff(new Date('2026-11-23T07:00:00Z'), plan))).toBe('2026-11-23T08:00:00.000Z')
  })

  test('the handoff instant itself moves on to the following week', () => {
    expect(iso(nextHandoff(new Date('2026-11-23T08:00:00Z'), plan))).toBe('2026-11-30T08:00:00.000Z')
  })

  test('keeps the wall-clock time across a DST change', () => {
    expect(iso(nextHandoff(new Date('2026-10-18T12:00:00Z'), plan))).toBe('2026-10-19T07:00:00.000Z')
    expect(iso(nextHandoff(new Date('2026-10-19T07:00:00Z'), plan))).toBe('2026-10-26T08:00:00.000Z')
  })

  test('reads the zone for a time zone far from UTC', () => {
    const tokyo = { ...plan, handoff_day: 'fri', handoff_time: '18:30', timezone: 'Asia/Tokyo' } as const
    expect(iso(nextHandoff(new Date('2026-11-21T12:00:00Z'), tokyo))).toBe('2026-11-27T09:30:00.000Z')
  })
})

describe('upcomingShifts', () => {
  const now = new Date('2026-11-21T12:00:00Z')

  test('without an anchor the first person is on call from now until the next handoff, then the list wraps', () => {
    const shifts = upcomingShifts(plan, now, 4)

    expect(shifts.map(({ userId, start, end }) => [userId, iso(start), iso(end)])).toEqual([
      ['petra', '2026-11-21T12:00:00.000Z', '2026-11-23T08:00:00.000Z'],
      ['bob', '2026-11-23T08:00:00.000Z', '2026-11-30T08:00:00.000Z'],
      ['carol', '2026-11-30T08:00:00.000Z', '2026-12-07T08:00:00.000Z'],
      ['petra', '2026-12-07T08:00:00.000Z', '2026-12-14T08:00:00.000Z'],
    ])
  })

  test('an anchor starts with the person on call until their shift ends, then the next in order', () => {
    const anchor = { userId: 'carol', until: new Date('2026-11-23T08:00:00Z') }

    const shifts = upcomingShifts(plan, now, 3, anchor)

    expect(shifts.map(({ userId, end }) => [userId, iso(end)])).toEqual([
      ['carol', '2026-11-23T08:00:00.000Z'],
      ['petra', '2026-11-30T08:00:00.000Z'],
      ['bob', '2026-12-07T08:00:00.000Z'],
    ])
  })

  test('ignores an anchor outside the rotation or already over', () => {
    const outside = { userId: 'dana', until: new Date('2026-11-23T08:00:00Z') }
    const over = { userId: 'bob', until: new Date('2026-11-20T08:00:00Z') }

    expect(upcomingShifts(plan, now, 1, outside)[0].userId).toBe('petra')
    expect(upcomingShifts(plan, now, 1, over)[0].userId).toBe('petra')
  })

  test('a rotation of one keeps the same person every week', () => {
    const shifts = upcomingShifts({ ...plan, user_ids: ['petra'] }, now, 3)

    expect(shifts.map(({ userId }) => userId)).toEqual(['petra', 'petra', 'petra'])
  })

  test('an empty rotation has no shifts', () => {
    expect(upcomingShifts({ ...plan, user_ids: [] }, now, 4)).toEqual([])
  })
})
