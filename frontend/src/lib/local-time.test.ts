import { expect, test } from 'vitest'
import { HOUR_MINUTE, toHourMinute } from './local-time'

test('toHourMinute drops seconds from API times and leaves other text alone', () => {
  expect(toHourMinute('09:00:00')).toBe('09:00')
  expect(toHourMinute('09:00')).toBe('09:00')
  expect(toHourMinute('9am')).toBe('9am')
})

test('HOUR_MINUTE takes 24-hour HH:MM only', () => {
  expect(['00:00', '09:30', '23:59'].every((time) => HOUR_MINUTE.test(time))).toBe(true)
  expect(['24:00', '9:30', '09:60', '09:30:00'].some((time) => HOUR_MINUTE.test(time))).toBe(false)
})
