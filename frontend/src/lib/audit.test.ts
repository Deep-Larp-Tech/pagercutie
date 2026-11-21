import { describe, expect, test } from 'vitest'
import { actionLabel, auditSearch, entityTypeLabel } from './audit'

describe('audit labels', () => {
  test.each([
    ['alert.acknowledged', 'Alert acknowledged'],
    ['step.approval_requested', 'Step approval requested'],
    ['rule.updated', 'Rule updated'],
    ['escalated', 'Escalated'],
  ])('action %s reads as "%s"', (action, label) => {
    expect(actionLabel(action)).toBe(label)
  })

  test('entity types read as words', () => {
    expect(entityTypeLabel('event_schema')).toBe('Event schema')
    expect(entityTypeLabel('alert')).toBe('Alert')
  })
})

describe('auditSearch', () => {
  test('keeps a type and any well-formed id', () => {
    const id = '00000000-0000-0000-0000-000000000000'
    expect(auditSearch.parse({ entity_type: ' alert ', entity_id: id })).toEqual({ entity_type: 'alert', entity_id: id })
  })

  test('drops values that do not parse', () => {
    expect(auditSearch.parse({ entity_type: '', entity_id: '0193c000' })).toEqual({})
    expect(auditSearch.parse({ entity_type: 'x'.repeat(51), entity_id: 42 })).toEqual({})
  })
})
