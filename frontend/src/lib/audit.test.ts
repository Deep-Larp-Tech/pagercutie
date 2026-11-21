import { describe, expect, test } from 'vitest'
import { auditActionText } from './audit'

describe('auditActionText', () => {
  test('known actions read as plain words', () => {
    expect(auditActionText('alert.acknowledged')).toBe('Acknowledged the alert')
    expect(auditActionText('step.approved')).toBe('Approved a step')
  })

  test('an unknown action falls back to its name in sentence case', () => {
    expect(auditActionText('alert.auto_resolved')).toBe('Alert auto resolved')
    expect(auditActionText('...')).toBe('Unknown action')
  })
})
