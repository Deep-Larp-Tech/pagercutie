import { describe, expect, test } from 'vitest'
import type { AlertEvent, AlertRead } from '@/api/generated/model'
import { alert, uuid } from '@/test/alerts'
import {
  applyAlertEvent,
  matchesFilters,
  mergeAlert,
  parseAlertEvent,
  pruneAlert,
  reloadAlerts,
  updateAlertList,
  type AlertFilters,
} from './alert-feed'

const teamId = uuid()
const any: AlertFilters = {}
const openOnly: AlertFilters = { status: ['open', 'acknowledged'] }

const created = (item: AlertRead): AlertEvent => ({ type: 'alert.created', alert: item })
const updated = (item: AlertRead): AlertEvent => ({ type: 'alert.updated', alert: item })
const ids = (list: AlertRead[]) => list.map((item) => item.id)

describe('matchesFilters', () => {
  test('an absent or empty list matches any value', () => {
    expect(matchesFilters(alert(teamId), {})).toBe(true)
    expect(matchesFilters(alert(teamId), { status: [], severity: [] })).toBe(true)
  })

  test('status and severity must both match', () => {
    const item = alert(teamId, { status: 'acknowledged', severity: 'warn' })
    expect(matchesFilters(item, { status: ['acknowledged'], severity: ['warn', 'error'] })).toBe(true)
    expect(matchesFilters(item, { status: ['open'] })).toBe(false)
    expect(matchesFilters(item, { severity: ['critical'] })).toBe(false)
  })
})

describe('applyAlertEvent', () => {
  test('alert.created adds the alert in last-seen order', () => {
    const older = alert(teamId, { last_seen_at: '2026-11-21T11:00:00Z' })
    const newer = alert(teamId, { last_seen_at: '2026-11-21T13:00:00Z' })
    const middle = alert(teamId, { last_seen_at: '2026-11-21T12:00:00Z' })

    const list = applyAlertEvent([newer, older], created(middle), any)

    expect(ids(list)).toEqual([newer.id, middle.id, older.id])
  })

  test('alert.created for an alert that does not match the filters is ignored', () => {
    const list = [alert(teamId)]
    const resolved = alert(teamId, { status: 'resolved' })

    expect(applyAlertEvent(list, created(resolved), openOnly)).toBe(list)
  })

  test('the same event twice adds one card', () => {
    const item = alert(teamId)

    const list = applyAlertEvent(applyAlertEvent([], created(item), any), created(item), any)

    expect(list).toHaveLength(1)
  })

  test('alert.updated with a new occurrence raises the counter and moves the alert to the top', () => {
    const other = alert(teamId, { last_seen_at: '2026-11-21T12:30:00Z' })
    const item = alert(teamId, { occurrences: 3 })
    const repeat = { ...item, occurrences: 4, last_seen_at: '2026-11-21T12:45:00Z' }

    const list = applyAlertEvent([other, item], updated(repeat), any)

    expect(ids(list)).toEqual([item.id, other.id])
    expect(list[0].occurrences).toBe(4)
  })

  test('an alert that stops matching stays until pruneAlert removes it', () => {
    const item = alert(teamId)
    const resolved = { ...item, status: 'resolved' as const, resolution: 'manual' as const }

    const list = applyAlertEvent([item], updated(resolved), openOnly)

    expect(list).toEqual([resolved])
    expect(pruneAlert(list, item.id, openOnly)).toEqual([])
  })

  test('pruneAlert keeps an alert that matches again and other alerts', () => {
    const item = alert(teamId)
    const list = [item]

    expect(pruneAlert(list, item.id, openOnly)).toBe(list)
  })
})

describe('out-of-order events', () => {
  const item = alert(teamId, { occurrences: 2 })
  const acknowledged: AlertRead = {
    ...item,
    status: 'acknowledged',
    acknowledged_by: uuid(),
    acknowledged_at: '2026-11-21T12:10:00Z',
  }
  const lateRepeat: AlertRead = { ...item, occurrences: 3, last_seen_at: '2026-11-21T12:05:00Z' }

  test('a stale open version does not undo an acknowledgement, and its occurrence still counts', () => {
    const [merged] = applyAlertEvent([acknowledged], updated(lateRepeat), any)

    expect(merged.status).toBe('acknowledged')
    expect(merged.acknowledged_by).toBe(acknowledged.acknowledged_by)
    expect(merged.occurrences).toBe(3)
    expect(merged.last_seen_at).toBe('2026-11-21T12:05:00Z')
  })

  test('the result is the same in either arrival order', () => {
    expect(mergeAlert(acknowledged, lateRepeat)).toEqual(mergeAlert(lateRepeat, acknowledged))
  })

  test('an older version arriving last changes nothing', () => {
    const latest: AlertRead = { ...item, occurrences: 5, last_seen_at: '2026-11-21T12:20:00Z' }

    expect(applyAlertEvent([latest], updated(item), any)).toEqual([latest])
  })

  test('escalations from both versions are kept', () => {
    const first = uuid()
    const second = uuid()
    const merged = mergeAlert(
      { ...item, escalated_team_ids: [first] },
      { ...acknowledged, escalated_team_ids: [second] },
    )

    expect(merged.escalated_team_ids.toSorted()).toEqual([first, second].toSorted())
  })
})

describe('reloadAlerts after a reconnect', () => {
  test('events received while the list loaded are replayed over an older snapshot', () => {
    const item = alert(teamId)
    const arrived = alert(teamId, { last_seen_at: '2026-11-21T12:30:00Z' })
    const repeat = { ...item, occurrences: 2, last_seen_at: '2026-11-21T12:40:00Z' }
    const snapshot = [item]

    const list = reloadAlerts(snapshot, [created(arrived), updated(repeat)], any)

    expect(ids(list)).toEqual([item.id, arrived.id])
    expect(list[0].occurrences).toBe(2)
  })

  test('events the snapshot already contains change nothing', () => {
    const item = alert(teamId, { occurrences: 4 })

    expect(reloadAlerts([item], [created({ ...item, occurrences: 3 }), updated(item)], any)).toEqual([item])
  })

  test('replayed events respect the filters', () => {
    const resolvedElsewhere = alert(teamId, { status: 'resolved' })

    expect(reloadAlerts([], [created(resolvedElsewhere)], openOnly)).toEqual([])
  })
})

describe('updateAlertList', () => {
  test('updates the alerts of a 200 answer', () => {
    const item = alert(teamId)
    const response = { status: 200 as const, data: [], headers: new Headers() }

    expect(updateAlertList(response, (list) => [...list, item])).toEqual({ ...response, data: [item] })
  })

  test('leaves other answers and an empty cache alone', () => {
    const response = { status: 401 as const, data: { detail: 'Sign in' }, headers: new Headers() }

    expect(updateAlertList(response, () => [alert(teamId)])).toBe(response)
    expect(updateAlertList(undefined, () => [alert(teamId)])).toBeUndefined()
  })
})

describe('parseAlertEvent', () => {
  test('reads a valid event', () => {
    const event = created(alert(teamId))

    expect(parseAlertEvent(JSON.stringify(event))).toEqual(event)
  })

  test('drops text that is not JSON, an unknown type and a malformed alert', () => {
    expect(parseAlertEvent('keep-alive')).toBeNull()
    expect(parseAlertEvent(JSON.stringify({ type: 'alert.deleted', alert: alert(teamId) }))).toBeNull()
    expect(parseAlertEvent(JSON.stringify({ type: 'alert.created', alert: { id: 'x' } }))).toBeNull()
  })

  test('keeps a field whose value is JSON null, shown as null', () => {
    const item = alert(teamId, { fields: [] })
    const json = JSON.stringify({ type: 'alert.updated', alert: { ...item, fields: [{ path: 'a', value: null }] } })

    expect(parseAlertEvent(json)?.alert.fields).toEqual([{ path: 'a', value: 'null' }])
  })
})
