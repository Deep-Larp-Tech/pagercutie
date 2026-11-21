import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { getGetMeUrl, getMe, type getMeResponse } from '@/api/generated/auth/auth'
import { server } from '@/test/server'
import { unexpectedStatusMessage } from './api'

function describeMe(response: getMeResponse) {
  switch (response.status) {
    case 200:
      return response.data.user.display_name
    case 401:
      return response.data.detail
    default:
      return unexpectedStatusMessage(response)
  }
}

describe('unexpectedStatusMessage', () => {
  test.each([
    [501, "This feature isn't available yet."],
    [502, 'Something went wrong on the server (HTTP 502). Try again in a moment.'],
  ])('explains an undocumented %i', async (status, message) => {
    server.use(http.get(getGetMeUrl(), () => HttpResponse.json({ detail: 'x' }, { status })))

    expect(describeMe(await getMe())).toBe(message)
  })
})
