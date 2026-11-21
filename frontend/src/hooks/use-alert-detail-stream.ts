import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  getGetAlertQueryKey,
  getGetRunbookRunQueryKey,
  getListAlertDeliveriesQueryKey,
  getStreamAlertsUrl,
  type getAlertResponse,
} from '@/api/generated/alerts/alerts'
import { getListAuditEntriesQueryKey } from '@/api/generated/audit/audit'
import { mergeAlert } from '@/lib/alert-feed'
import { openAlertStream } from '@/lib/alert-stream'

/**
 * Keeps an open alert detail current (ADR-0097): any event for `alertId` merges into the
 * `GET /alerts/{id}` cache and reloads the runbook run, deliveries and history, which have no stream of their own.
 * The server announces every step the executor or a person moves on, so `RUN-3`'s buttons appear without a page
 * reload. A reopened connection reloads all four, since events may have been missed while it was down.
 */
export function useAlertDetailStream(alertId: string) {
  const queryClient = useQueryClient()
  useEffect(() => {
    const alertKey = getGetAlertQueryKey(alertId)
    const reloadParts = () => {
      void queryClient.invalidateQueries({ queryKey: getGetRunbookRunQueryKey(alertId), exact: true })
      void queryClient.invalidateQueries({ queryKey: getListAlertDeliveriesQueryKey(alertId), exact: true })
      void queryClient.invalidateQueries({ queryKey: getListAuditEntriesQueryKey() })
    }
    let dropped = false
    const connection = openAlertStream(getStreamAlertsUrl(), {
      onOpen: () => {
        if (!dropped) return
        dropped = false
        void queryClient.invalidateQueries({ queryKey: alertKey, exact: true })
        reloadParts()
      },
      onEvent: (event) => {
        if (event.alert.id !== alertId) return
        queryClient.setQueryData<getAlertResponse>(alertKey, (response) =>
          response?.status === 200 ? { ...response, data: mergeAlert(response.data, event.alert) } : response,
        )
        reloadParts()
      },
      onDrop: () => {
        dropped = true
      },
    })
    return connection.close
  }, [alertId, queryClient])
}
