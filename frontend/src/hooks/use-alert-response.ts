import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  getListAlertsQueryKey,
  useAcknowledgeAlert,
  useResolveAlert,
  type listAlertsResponse,
} from '@/api/generated/alerts/alerts'
import type { AlertRead } from '@/api/generated/model'
import { mergeAlert, replaceAlert, updateAlertList } from '@/lib/alert-feed'
import { unexpectedStatusMessage } from '@/lib/api'
import { useMe } from '@/lib/session'

/** What the user asked for on an alert card. */
type Response = 'acknowledge' | 'resolve'

const failed = {
  acknowledge: "Couldn't acknowledge the alert. Try again.",
  resolve: "Couldn't resolve the alert. Try again.",
} as const satisfies Record<Response, string>

const offline = "Couldn't reach the server. Check your connection and try again."
const changed = 'Someone else changed this alert first. The feed now shows its current state.'
const forbidden = "You can't respond to this alert. Ask a team lead for the member role."
const missing = "This alert no longer exists, or you can't see it any more."

/**
 * Acknowledge and Resolve for one alert card. Both update every cached feed at once (optimistic), put the alert back
 * as it was when the API refuses, and reload the feeds, since a `409` means the alert changed elsewhere.
 */
export function useAlertResponse(alert: AlertRead) {
  const me = useMe()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const listKey = getListAlertsQueryKey()

  // Every `GET /alerts` entry shares the key prefix `/api/alerts`; the stream and single-alert keys do not.
  const updateFeeds = (update: (list: AlertRead[]) => AlertRead[]) =>
    queryClient.setQueriesData<listAlertsResponse>({ queryKey: listKey }, (response) =>
      updateAlertList(response, update),
    )

  const start = (next: AlertRead) => {
    setError(null)
    updateFeeds((list) => replaceAlert(list, next))
  }

  const succeed = (saved: AlertRead, message: string) => {
    updateFeeds((list) => list.map((item) => (item.id === saved.id ? mergeAlert(item, saved) : item)))
    toast.success(message)
  }

  const fail = (message: string | null) => {
    updateFeeds((list) => replaceAlert(list, alert))
    setError(message)
    void queryClient.invalidateQueries({ queryKey: listKey })
  }

  const acknowledgeMutation = useAcknowledgeAlert({
    mutation: {
      onMutate: () =>
        start({
          ...alert,
          status: 'acknowledged',
          acknowledged_by: me.user.id,
          acknowledged_at: new Date().toISOString(),
        }),
      onSuccess: (response) => {
        switch (response.status) {
          case 200:
            return succeed(response.data, 'Alert acknowledged')
          case 401:
            return fail(null)
          case 403:
            return fail(forbidden)
          case 404:
            return fail(missing)
          case 409:
            return fail(changed)
          case 422:
            return fail(failed.acknowledge)
          default:
            return fail(unexpectedStatusMessage(response))
        }
      },
      onError: () => fail(offline),
    },
  })

  const resolveMutation = useResolveAlert({
    mutation: {
      onMutate: () =>
        start({
          ...alert,
          status: 'resolved',
          resolved_by: me.user.id,
          resolved_at: new Date().toISOString(),
          resolution: 'manual',
        }),
      onSuccess: (response) => {
        switch (response.status) {
          case 200:
            return succeed(response.data, 'Alert resolved')
          case 401:
            return fail(null)
          case 403:
            return fail(forbidden)
          case 404:
            return fail(missing)
          case 409:
            return fail(changed)
          case 400:
          case 422:
            return fail(failed.resolve)
          default:
            return fail(unexpectedStatusMessage(response))
        }
      },
      onError: () => fail(offline),
    },
  })

  return {
    acknowledge: () => acknowledgeMutation.mutate({ alertId: alert.id }),
    resolve: () => resolveMutation.mutate({ alertId: alert.id, data: {} }),
    /** Inline message after a refused or failed request; `null` otherwise. */
    error,
  }
}
