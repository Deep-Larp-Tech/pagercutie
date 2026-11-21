import { describe, expect, test } from 'vitest'
import type { ChannelRule } from '@/api/generated/model'
import { describeDays, describeRule } from './preferences'

describe('describeRule', () => {
  test("Anna's two rules from DOMAIN.md §5", () => {
    const daytime: ChannelRule = {
      min_severity: 'critical',
      channels: ['sms'],
      window: { days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], start: '08:00', end: '20:00' },
    }
    const otherwise: ChannelRule = { min_severity: 'critical', channels: ['email'] }

    expect(describeRule(daytime)).toBe('Critical and above: SMS, every day 08:00 to 20:00')
    expect(describeRule(otherwise)).toBe('Critical and above: Email, at any time')
  })

  test('weekday working hours', () => {
    const rule: ChannelRule = {
      min_severity: 'critical',
      channels: ['sms'],
      window: { days: ['mon', 'tue', 'wed', 'thu', 'fri'], start: '08:00:00', end: '20:00:00' },
    }

    expect(describeRule(rule)).toBe('Critical and above: SMS, weekdays 08:00 to 20:00')
  })

  test('a window that ends before it starts runs into the next day', () => {
    const rule: ChannelRule = {
      min_severity: 'error',
      channels: ['phone', 'email'],
      window: { days: ['sat', 'sun'], start: '22:00', end: '06:00' },
    }

    expect(describeRule(rule)).toBe('Error and above: Phone call, Email, weekends 22:00 to 06:00 the next day')
  })

  test('debug matches any severity', () => {
    expect(describeRule({ min_severity: 'debug', channels: ['ui'], window: null })).toBe('Any severity: UI, at any time')
  })

  test('warn reads as Warning', () => {
    expect(describeRule({ min_severity: 'warn', channels: ['email'] })).toBe('Warning and above: Email, at any time')
  })
})

describe('describeDays', () => {
  test('lists other days Monday first, whatever the input order', () => {
    expect(describeDays(['fri', 'mon', 'wed'])).toBe('Mon, Wed, Fri')
  })

  test('omitted days mean every day, as the API reads them', () => {
    expect(describeDays(undefined)).toBe('every day')
  })
})
