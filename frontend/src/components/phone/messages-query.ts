import { getListMyMessagesQueryOptions } from '@/api/generated/alerts/alerts'
import type { Channel } from '@/api/generated/model'

/** How often the phone page asks for new messages while the tab is visible; `GET /me/messages` has no stream. */
export const MESSAGES_POLL_MS = 10_000

/**
 * `GET /me/messages` for `channels`, polled every `MESSAGES_POLL_MS` while it answers `200`. Polling pauses while the
 * tab is hidden (`refetchIntervalInBackground: false`) and stops on any other status, so a `501` stub isn't polled.
 */
export function myMessagesQueryOptions(channels: Channel[]) {
  return getListMyMessagesQueryOptions(
    { channel: channels },
    {
      query: {
        refetchInterval: (query) => (query.state.data?.status === 200 ? MESSAGES_POLL_MS : false),
        refetchIntervalInBackground: false,
      },
    },
  )
}
