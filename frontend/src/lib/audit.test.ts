import { describe, expect, test } from 'vitest'
import { AuditAction } from '@/api/generated/model'
import {
  actionEntityType,
  actionsOf,
  auditActionText,
  auditQuery,
  auditSearch,
  entityTypeLabel,
  isFiltered,
} from './audit'

const id = '00000000-0000-0000-0000-000000000000'
const other = '00000000-0000-0000-0000-000000000001'
const anchor = Date.parse('2026-11-21T12:00:00Z')

describe('auditActionText', () => {
  test('actions read as plain words', () => {
    expect(auditActionText('alert.acknowledged')).toBe('Acknowledged the alert')
    expect(auditActionText('step.approved')).toBe('Approved a step')
    expect(auditActionText('team.rotation_updated')).toBe('Changed the on-call rotation')
  })
})

describe('entityTypeLabel', () => {
  test('entity types read as words', () => {
    expect(entityTypeLabel('event_schema')).toBe('Event schema')
    expect(entityTypeLabel('alert')).toBe('Alert')
  })
})

describe('actionEntityType', () => {
  test('dotted actions name their prefix; step actions name the alert', () => {
    for (const action of Object.values(AuditAction)) {
      const prefix = action.split('.')[0]
      expect(actionEntityType[action]).toBe(prefix === 'step' ? 'alert' : prefix)
    }
  })

  test('actionsOf lists the actions of one type', () => {
    expect(actionsOf('source')).toEqual(['source.created', 'source.updated', 'source.deleted', 'source.token_rotated'])
    expect(actionsOf('alert')).toContain('step.done')
  })
})

describe('auditSearch', () => {
  test('keeps every well-formed filter', () => {
    const search = {
      entity_type: 'alert',
      entity_id: id,
      action: 'alert.resolved',
      actor_user_id: other,
      system: true,
      team_id: id,
      without_team: true,
      range: '24h',
    }
    expect(auditSearch.parse(search)).toEqual(search)
  })

  test('drops values that do not parse', () => {
    expect(
      auditSearch.parse({
        entity_type: 'widget',
        entity_id: '0193c000',
        action: 'rule.exploded',
        actor_user_id: 42,
        system: 'yes',
        without_team: false,
        range: '2y',
      }),
    ).toEqual({})
  })
})

describe('auditQuery', () => {
  test('no filters ask for every entry', () => {
    expect(auditQuery({}, undefined, anchor)).toEqual({
      team_id: undefined,
      without_team: undefined,
      entity_type: undefined,
      entity_id: undefined,
      actor_user_id: undefined,
      system: undefined,
      action: undefined,
      since: undefined,
    })
  })

  test('a range counts back from the anchor; an action goes as a one-item list', () => {
    expect(auditQuery({ range: '24h', action: 'rule.updated' }, undefined, anchor)).toMatchObject({
      since: '2026-11-20T12:00:00.000Z',
      action: ['rule.updated'],
    })
    expect(auditQuery({ range: '1h' }, undefined, anchor).since).toBe('2026-11-21T11:00:00.000Z')
  })

  test('a team page replaces the address team and never sends without_team', () => {
    expect(auditQuery({ team_id: other, without_team: true }, id, anchor)).toMatchObject({
      team_id: id,
      without_team: undefined,
    })
  })

  test('of each pair the API rejects together, the specific one is sent', () => {
    const both = { actor_user_id: id, system: true, team_id: other, without_team: true } as const
    expect(auditQuery(both, undefined, anchor)).toMatchObject({
      actor_user_id: id,
      system: undefined,
      team_id: other,
      without_team: undefined,
    })
    expect(auditQuery({ system: true, without_team: true }, undefined, anchor)).toMatchObject({
      system: true,
      without_team: true,
    })
  })
})

describe('isFiltered', () => {
  test('any set filter counts', () => {
    expect(isFiltered({})).toBe(false)
    expect(isFiltered({ entity_type: undefined })).toBe(false)
    expect(isFiltered({ range: '7d' })).toBe(true)
  })
})
