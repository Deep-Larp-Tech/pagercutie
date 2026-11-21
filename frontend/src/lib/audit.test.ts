import { describe, expect, test } from 'vitest'
import { auditActionText, auditSearch, entityTypeLabel } from './audit'

describe('auditActionText', () => {
  test('known actions read as plain words', () => {
    expect(auditActionText('alert.acknowledged')).toBe('Acknowledged the alert')
    expect(auditActionText('step.approved')).toBe('Approved a step')
  })

  test.each([
    ['alert.auto_resolved', 'Alert auto resolved'],
    ['step.approval_requested', 'Step approval requested'],
    ['rule.updated', 'Rule updated'],
    ['escalated', 'Escalated'],
    ['...', 'Unknown action'],
  ])('an action without words, %s, reads as "%s"', (action, label) => {
    expect(auditActionText(action)).toBe(label)
  })
})

describe('entityTypeLabel', () => {
  test('entity types read as words', () => {
    expect(entityTypeLabel('event_schema')).toBe('Event schema')
    expect(entityTypeLabel('alert')).toBe('Alert')
  })
})

describe('auditSearch', () => {
  test('keeps a type and any well-formed id', () => {
    const id = '00000000-0000-0000-0000-000000000000'
    expect(auditSearch.parse({ entity_type: 'alert', entity_id: id })).toEqual({ entity_type: 'alert', entity_id: id })
  })

  test('drops values that do not parse', () => {
    expect(auditSearch.parse({ entity_type: '', entity_id: '0193c000' })).toEqual({})
    expect(auditSearch.parse({ entity_type: 'widget', entity_id: 42 })).toEqual({})
  })
})
