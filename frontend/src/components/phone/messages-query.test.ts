import { describe, expect, test } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import type { listMyMessagesResponse } from '@/api/generated/alerts/alerts'
import type { ErrorRead, HTTPValidationError } from '@/api/generated/model'
import { MESSAGES_POLL_MS, myMessagesQueryOptions } from './messages-query'

describe('myMessagesQueryOptions', () => {
  test('asks for the given channels and polls only while the endpoint answers 200', () => {
    const queryClient = new QueryClient()
    const options = myMessagesQueryOptions(['sms', 'phone'])
    expect(options.queryKey).toEqual(['/api/me/messages', { channel: ['sms', 'phone'] }])
    expect(options.refetchIntervalInBackground).toBe(false)

    const interval = options.refetchInterval
    if (typeof interval !== 'function') throw new Error('refetchInterval should depend on the answer')
    const intervalAfter = (response: Parameters<typeof queryClient.setQueryData<listMyMessagesResponse>>[1]) => {
      queryClient.setQueryData(options.queryKey, response)
      const query = queryClient.getQueryCache().find<listMyMessagesResponse, ErrorRead | HTTPValidationError>({
        queryKey: options.queryKey,
      })
      if (query === undefined) throw new Error('query not cached')
      return interval(query)
    }

    expect(intervalAfter({ status: 200, data: [], headers: new Headers() })).toBe(MESSAGES_POLL_MS)
    expect(intervalAfter({ status: 401, data: { detail: 'Not signed in.' }, headers: new Headers() })).toBe(false)
  })
})
