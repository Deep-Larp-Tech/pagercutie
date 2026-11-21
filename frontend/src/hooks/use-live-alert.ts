import { useEffect, useState } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { getListAlertsQueryKey, type listAlertsResponse } from '@/api/generated/alerts/alerts'
import type { AlertRead } from '@/api/generated/model'
import { mergeAlert } from '@/lib/alert-feed'

const [listKey] = getListAlertsQueryKey()

/** Alert `id` merged from every cached `GET /alerts` answer that holds it; `undefined` when none does. */
function findInFeeds(queryClient: QueryClient, id: string): AlertRead | undefined {
  let found: AlertRead | undefined
  for (const [, response] of queryClient.getQueriesData<listAlertsResponse>({ queryKey: [listKey] })) {
    if (response?.status !== 200) continue
    const alert = response.data.find((item) => item.id === id)
    if (alert !== undefined) found = found === undefined ? alert : mergeAlert(found, alert)
  }
  return found
}

/**
 * `fetched` (the `GET /alerts/{id}` answer) merged with the same alert in any cached feed, which the live stream keeps
 * current (ADR-0054), so a change made there (an optimistic acknowledge) shows here too. The detail's own stream
 * (`useAlertDetailStream`, ADR-0098) keeps `fetched` current. Mount it with `key={id}`: the first lookup happens once,
 * on mount.
 */
export function useLiveAlert(fetched: AlertRead): AlertRead {
  const queryClient = useQueryClient()
  const { id } = fetched
  const [cached, setCached] = useState(() => findInFeeds(queryClient, id))
  useEffect(() => {
    const cache = queryClient.getQueryCache()
    return cache.subscribe((event) => {
      if (event.type === 'updated' && event.query.queryKey[0] === listKey) setCached(findInFeeds(queryClient, id))
    })
  }, [queryClient, id])
  return cached === undefined ? fetched : mergeAlert(fetched, cached)
}
