import { describe, expect, test } from 'vitest'
import { formatFullTime, formatShortTime, isKnownTimeZone, timeZoneOptions, utcOffsetLabel } from './datetime'

const now = new Date('2026-11-21T12:00:00Z')

describe('formatShortTime', () => {
  test('shows only the time for today in the given zone', () => {
    expect(formatShortTime('2026-11-21T13:02:00Z', 'Europe/Prague', now)).toBe('14:02')
  })

  test('adds the day for another day', () => {
    expect(formatShortTime('2026-11-20T13:02:00Z', 'Europe/Prague', now)).toBe('20 Nov, 14:02')
  })

  test('adds the year for an earlier year', () => {
    expect(formatShortTime('2025-11-20T13:02:00Z', 'Europe/Prague', now)).toBe('20 Nov 2025, 14:02')
  })

  test('compares days in the given zone, not in UTC', () => {
    expect(formatShortTime('2026-11-20T23:30:00Z', 'Europe/Prague', now)).toBe('00:30')
  })

  test('an unknown zone falls back to the browser zone instead of throwing', () => {
    expect(() => formatShortTime('2026-11-21T13:02:00Z', 'Mars/Olympus', now)).not.toThrow()
    expect(() => formatFullTime('2026-11-21T13:02:00Z', 'Mars/Olympus')).not.toThrow()
  })
})

describe('time zones', () => {
  test('the options include UTC, the current zone and the browser list, sorted', () => {
    const options = timeZoneOptions('Europe/Prague')
    expect(options).toContain('UTC')
    expect(options).toContain('Asia/Tokyo')
    expect(options).toEqual(options.toSorted((a, b) => a.localeCompare(b)))
    expect(new Set(options).size).toBe(options.length)
  })

  test('a saved zone the browser does not list stays an option', () => {
    expect(timeZoneOptions('Etc/GMT+5')).toContain('Etc/GMT+5')
  })

  test('isKnownTimeZone and utcOffsetLabel', () => {
    expect(isKnownTimeZone('Europe/Prague')).toBe(true)
    expect(isKnownTimeZone('Mars/Olympus')).toBe(false)
    expect(utcOffsetLabel('Asia/Tokyo')).toBe('GMT+9')
    expect(utcOffsetLabel('Mars/Olympus')).toBe('')
  })
})
