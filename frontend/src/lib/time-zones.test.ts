import { describe, expect, test } from 'vitest'
import { timeZoneOptions } from './time-zones'

describe('timeZoneOptions', () => {
  test('lists the IANA zones sorted, with UTC and the current value even when the browser omits them', () => {
    const zones = timeZoneOptions('Europe/Kiev')
    expect(zones).toContain('Europe/Prague')
    expect(zones).toContain('UTC')
    expect(zones).toContain('Europe/Kiev')
    expect(zones).toEqual(zones.toSorted((a, b) => a.localeCompare(b)))
    expect(new Set(zones).size).toBe(zones.length)
  })
})
