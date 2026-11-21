import * as zod from 'zod'
import { GetAlertResponse } from '@/api/generated/alerts/alerts.zod'
import type { listAlertsResponse } from '@/api/generated/alerts/alerts'
import {
  AlertEventType,
  type AlertEvent,
  type AlertRead,
  type AlertStatus,
  type JsonValue,
  type Severity,
} from '@/api/generated/model'

/** Status and severity filters of a feed; an absent or empty list means any value. */
export interface AlertFilters {
  status?: readonly AlertStatus[]
  severity?: readonly Severity[]
}

/** Lifecycle order (DOMAIN.md §6); an alert's status only moves up this scale. */
const statusRank = {
  open: 0,
  acknowledged: 1,
  resolved: 2,
} as const satisfies Record<AlertStatus, number>

/** Whether `alert` passes `filters`. */
export function matchesFilters(alert: AlertRead, { status, severity }: AlertFilters): boolean {
  if (status !== undefined && status.length > 0 && !status.includes(alert.status)) return false
  if (severity !== undefined && severity.length > 0 && !severity.includes(alert.severity)) return false
  return true
}

function later(a: string, b: string): string {
  return Date.parse(a) >= Date.parse(b) ? a : b
}

function rankOrder(a: AlertRead, b: AlertRead): number {
  return (
    statusRank[a.status] - statusRank[b.status] ||
    Date.parse(a.last_seen_at) - Date.parse(b.last_seen_at) ||
    a.occurrences - b.occurrences
  )
}

/**
 * Combines two versions of one alert, whatever order they arrived in: status, acknowledgement and resolution come
 * from the further-along version, `occurrences` and `last_seen_at` take the maximum, escalations are united. Merging
 * the same version twice changes nothing, so events can be replayed over a reloaded list.
 */
export function mergeAlert(a: AlertRead, b: AlertRead): AlertRead {
  const [older, newer] = rankOrder(a, b) <= 0 ? [a, b] : [b, a]
  return {
    ...newer,
    occurrences: Math.max(older.occurrences, newer.occurrences),
    last_seen_at: later(older.last_seen_at, newer.last_seen_at),
    escalated_team_ids: [...new Set([...newer.escalated_team_ids, ...older.escalated_team_ids])],
  }
}

/** Most recently seen first, the order `GET /alerts` answers in. */
function byLastSeen(list: AlertRead[]): AlertRead[] {
  return list.toSorted((a, b) => Date.parse(b.last_seen_at) - Date.parse(a.last_seen_at))
}

/**
 * Applies one live feed event to a feed's list. A known alert is merged in place, even when it stops matching the
 * filters (the feed removes it 700 ms later with `pruneAlert`, so a resolve can show before the card leaves). An
 * unknown alert is added only when it matches the filters.
 */
export function applyAlertEvent(list: AlertRead[], event: AlertEvent, filters: AlertFilters): AlertRead[] {
  const incoming = event.alert
  const index = list.findIndex((alert) => alert.id === incoming.id)
  if (index === -1) return matchesFilters(incoming, filters) ? byLastSeen([...list, incoming]) : list
  return byLastSeen(list.with(index, mergeAlert(list[index], incoming)))
}

/** `list` without alert `id` when it no longer matches `filters`; the feed calls it 700 ms after the alert stops matching. */
export function pruneAlert(list: AlertRead[], id: string, filters: AlertFilters): AlertRead[] {
  const kept = list.filter((alert) => alert.id !== id || matchesFilters(alert, filters))
  return kept.length === list.length ? list : kept
}

/**
 * A reloaded list (`GET /alerts` after a (re)connect, DOMAIN.md §7) with the events received while it loaded applied
 * on top, so a snapshot older than those events does not undo them.
 */
export function reloadAlerts(fresh: AlertRead[], received: readonly AlertEvent[], filters: AlertFilters): AlertRead[] {
  return received.reduce((list, event) => applyAlertEvent(list, event, filters), fresh)
}

/** `list` with the alert of the same id replaced by `alert`, without merging; for optimistic updates and rollback. */
export function replaceAlert(list: AlertRead[], alert: AlertRead): AlertRead[] {
  const index = list.findIndex((item) => item.id === alert.id)
  return index === -1 ? list : list.with(index, alert)
}

/** Applies `update` to the alerts of a `GET /alerts` answer; other statuses and an empty cache stay as they are. */
export function updateAlertList(
  response: listAlertsResponse | undefined,
  update: (list: AlertRead[]) => AlertRead[],
): listAlertsResponse | undefined {
  if (response?.status !== 200) return response
  const data = update(response.data)
  return data === response.data ? response : { ...response, data }
}

// `JsonValue` is generated as `{}`, which leaves out JSON null although the API sends it; the string keeps the
// rendering of a null field without claiming a type the value does not have.
const jsonValue = zod.unknown().transform((value): JsonValue => value ?? 'null')

/** One live feed message (`AlertEvent`), assembled from the generated `AlertRead` schema; orval drops SSE item schemas. */
const alertEventSchema = zod.object({
  type: zod.enum(AlertEventType),
  alert: GetAlertResponse.extend({
    fields: zod.array(zod.object({ path: zod.string(), value: jsonValue })),
  }),
})

/** The event in one SSE message's `data`, or `null` when it is not JSON or not a valid `AlertEvent`. */
export function parseAlertEvent(data: string): AlertEvent | null {
  let json: unknown
  try {
    json = JSON.parse(data)
  } catch {
    return null
  }
  const result = alertEventSchema.safeParse(json)
  return result.success ? result.data : null
}
