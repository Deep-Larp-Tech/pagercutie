import { getListDeliveriesQueryOptions } from '@/api/generated/alerts/alerts'
import type { Channel } from '@/api/generated/model'

/** How often the open drawer asks for new deliveries while the tab is visible; `GET /deliveries` has no stream. */
export const DELIVERIES_POLL_MS = 5_000

/** The most deliveries one request asks for (the API's page limit). */
export const DELIVERIES_LIMIT = 100

/** Poll interval for the last answer's status: `DELIVERIES_POLL_MS` after a `200`, otherwise no polling. */
export function deliveriesPollInterval(status: number | undefined): number | false {
  return status === 200 ? DELIVERIES_POLL_MS : false
}

/**
 * `GET /deliveries`, newest first, for `channels` (every channel when omitted). Polled every `DELIVERIES_POLL_MS`
 * while it answers `200`; polling pauses while the tab is hidden and stops on any other status, so a `501` stub
 * isn't polled.
 */
export function deliveriesQueryOptions(channels?: Channel[]) {
  return getListDeliveriesQueryOptions(
    channels === undefined ? { limit: DELIVERIES_LIMIT } : { limit: DELIVERIES_LIMIT, channel: channels },
    {
      query: {
        refetchInterval: (query) => deliveriesPollInterval(query.state.data?.status),
        refetchIntervalInBackground: false,
      },
    },
  )
}
