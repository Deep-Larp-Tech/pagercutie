import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getListAlertsQueryOptions, getStreamAlertsUrl } from '@/api/generated/alerts/alerts'
import type { AlertEvent, AlertRead, ListAlertsParams } from '@/api/generated/model'
import {
  applyAlertEvent,
  matchesFilters,
  parseAlertEvent,
  pruneAlert,
  reloadAlerts,
  updateAlertList,
  type AlertFilters,
} from '@/lib/alert-feed'
import { RESOLVE_EXIT_MS } from '@/lib/motion'

/** State of the live feed connection (DESIGN.md §9 "Live connection"). */
export type ConnectionState =
  /** The first connection is being opened; nothing is shown. */
  | 'connecting'
  /** Events arrive; nothing is shown. */
  | 'connected'
  /** The connection dropped less than `OFFLINE_AFTER_MS` ago and is being reopened. */
  | 'reconnecting'
  /** The connection has been down for `OFFLINE_AFTER_MS` or more; reconnecting continues in the background. */
  | 'offline'

/** How long the connection may be down before the feed says live updates are paused (ms). */
export const OFFLINE_AFTER_MS = 10_000

/** How long a connection must stay open before the reconnect delay starts again from 1 s (ms). */
export const STABLE_AFTER_MS = 5_000

/** Largest page `GET /alerts` allows; the feed shows at most this many alerts. */
export const ALERTS_PAGE_LIMIT = 100

/** Delay before reconnect attempt `attempt` (0-based): 1 s doubling up to 30 s (ms). */
export function reconnectDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 30_000)
}

/** Options for `useAlertStream`. */
export interface AlertStreamOptions {
  /** The team whose feed to show; omit for every alert the user can see (the Overview). */
  teamId?: string
  filters: AlertFilters
  /** Called for an `alert.created` event that adds a card to this feed, e.g. to announce it. */
  onAlertCreated?: (alert: AlertRead) => void
}

function nonEmpty<T>(values: readonly T[] | undefined): T[] | undefined {
  return values === undefined || values.length === 0 ? undefined : [...values]
}

/**
 * A live alert feed (`UI-1`, ADR-0012, ADR-0050): `GET /alerts` through the generated query, kept current by the
 * `GET /alerts/stream` events, which are merged into the same query cache entry. Every (re)connect reloads the list
 * and replays the events that arrived meanwhile (DOMAIN.md §7); a dropped connection is reopened with backoff.
 */
export function useAlertStream({ teamId, filters, onAlertCreated }: AlertStreamOptions) {
  const queryClient = useQueryClient()
  const params: ListAlertsParams = {
    limit: ALERTS_PAGE_LIMIT,
    team_id: teamId,
    status: nonEmpty(filters.status),
    severity: nonEmpty(filters.severity),
  }
  const options = getListAlertsQueryOptions(params)
  const query = useQuery(options)
  const { queryKey } = options

  // The stream outlives filter changes; its handlers read the current key and filters from here.
  const latest = useRef({ queryKey, filters, onAlertCreated })
  useEffect(() => {
    latest.current = { queryKey, filters, onAlertCreated }
  })

  const exitTimers = useRef(new Map<string, ReturnType<typeof setTimeout>>())
  const { data } = query
  useEffect(() => {
    if (data?.status !== 200) return
    const timers = exitTimers.current
    for (const alert of data.data) {
      if (timers.has(alert.id) || matchesFilters(alert, latest.current.filters)) continue
      const timer = setTimeout(() => {
        timers.delete(alert.id)
        const current = latest.current
        queryClient.setQueryData(current.queryKey, (response) =>
          updateAlertList(response, (list) => pruneAlert(list, alert.id, current.filters)),
        )
      }, RESOLVE_EXIT_MS)
      timers.set(alert.id, timer)
    }
  }, [data, queryClient])
  useEffect(() => {
    const timers = exitTimers.current
    return () => {
      for (const timer of timers.values()) clearTimeout(timer)
      timers.clear()
    }
  }, [])

  const [connection, setConnection] = useState<ConnectionState>('connecting')
  const retryRef = useRef<() => void>(() => {})
  const url = getStreamAlertsUrl(teamId === undefined ? undefined : { team_id: teamId })

  useEffect(() => {
    let source: EventSource | undefined
    let attempt = 0
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let offlineTimer: ReturnType<typeof setTimeout> | undefined
    let stableTimer: ReturnType<typeof setTimeout> | undefined
    // Events received while the list reloads, replayed over the reloaded list.
    let received: AlertEvent[] | undefined

    const apply = (event: AlertEvent) => {
      const { queryKey: key, filters: current, onAlertCreated: announce } = latest.current
      const before = queryClient.getQueryData(key)
      const known = before?.status === 200 && before.data.some((alert) => alert.id === event.alert.id)
      queryClient.setQueryData(key, (response) =>
        updateAlertList(response, (list) => applyAlertEvent(list, event, current)),
      )
      received?.push(event)
      if (event.type === 'alert.created' && !known && matchesFilters(event.alert, current)) announce?.(event.alert)
    }

    const reload = async () => {
      const buffer: AlertEvent[] = []
      received = buffer
      await queryClient.refetchQueries({ queryKey: latest.current.queryKey, exact: true })
      if (received === buffer) received = undefined
      const { queryKey: key, filters: current } = latest.current
      queryClient.setQueryData(key, (response) =>
        updateAlertList(response, (list) => reloadAlerts(list, buffer, current)),
      )
    }

    const startOfflineTimer = () => {
      offlineTimer = setTimeout(() => setConnection('offline'), OFFLINE_AFTER_MS)
    }

    const connect = () => {
      const current = new EventSource(url)
      source = current
      current.onopen = () => {
        clearTimeout(offlineTimer)
        offlineTimer = undefined
        setConnection('connected')
        stableTimer = setTimeout(() => {
          attempt = 0
        }, STABLE_AFTER_MS)
        void reload()
      }
      current.onmessage = (message) => {
        const payload: unknown = message.data
        if (typeof payload !== 'string') return
        const event = parseAlertEvent(payload)
        // An invalid message is dropped; the next reload brings the list back in line.
        if (event !== null) apply(event)
      }
      current.onerror = () => {
        current.close()
        clearTimeout(stableTimer)
        setConnection((state) => (state === 'offline' ? state : 'reconnecting'))
        if (offlineTimer === undefined) startOfflineTimer()
        retryTimer = setTimeout(connect, reconnectDelay(attempt))
        attempt += 1
      }
    }

    retryRef.current = () => {
      source?.close()
      clearTimeout(retryTimer)
      clearTimeout(stableTimer)
      clearTimeout(offlineTimer)
      attempt = 0
      setConnection('reconnecting')
      startOfflineTimer()
      connect()
    }
    connect()

    return () => {
      source?.close()
      clearTimeout(retryTimer)
      clearTimeout(offlineTimer)
      clearTimeout(stableTimer)
      retryRef.current = () => {}
    }
  }, [url, queryClient])

  return {
    /** The `GET /alerts` query; its data holds the live list. */
    query,
    connection,
    /** Reconnects now, for the Retry button of the offline state. */
    retry: () => retryRef.current(),
  }
}
