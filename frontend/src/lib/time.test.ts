import { describe, expect, test } from 'vitest'
import { absoluteTime, relativeTime, weekdayTime } from './time'

const now = Date.parse('2026-11-21T12:00:00Z')

describe('relativeTime', () => {
  test.each([
    ['2026-11-21T11:59:40Z', 'now'],
    ['2026-11-21T11:57:00Z', '3 minutes ago'],
    ['2026-11-21T10:00:00Z', '2 hours ago'],
    ['2026-11-20T12:00:00Z', 'yesterday'],
    ['2026-11-18T12:00:00Z', '3 days ago'],
  ])('%s reads %s', (iso, expected) => {
    expect(relativeTime(iso, now)).toBe(expected)
  })
})

test('absoluteTime uses the given time zone', () => {
  expect(absoluteTime('2026-11-23T08:00:00Z', 'Europe/Prague')).toBe('23 Nov 2026, 09:00')
})

test('weekdayTime gives the short weekday and a 24-hour time', () => {
  expect(weekdayTime('2026-11-23T08:00:00Z', 'Europe/Prague')).toBe('Mon 09:00')
})

test('an invalid time zone falls back to the browser zone instead of throwing', () => {
  expect(absoluteTime('2026-11-23T08:00:00Z', 'Not/AZone')).toBe(absoluteTime('2026-11-23T08:00:00Z'))
})
