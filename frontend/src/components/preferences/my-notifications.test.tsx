import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import type { ChannelPreferences } from '@/api/generated/model'
import {
  getGetUserChannelPreferencesUrl,
  getSetUserChannelPreferencesUrl,
  getUserChannelPreferences,
  setUserChannelPreferences,
} from '@/api/generated/users/users'
import { respond } from '@/test/http'
import { server } from '@/test/server'
import { openAs, petraIn, recordRequests } from '@/test/teams'

const PATH = '/me/notifications'
const me = petraIn('member')
const getUrl = getGetUserChannelPreferencesUrl(me.user.id)
const putUrl = getSetUserChannelPreferencesUrl(me.user.id)

const anna: ChannelPreferences = {
  rules: [
    {
      min_severity: 'critical',
      channels: ['sms'],
      window: { days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], start: '08:00:00', end: '20:00:00' },
    },
    { min_severity: 'critical', channels: ['email'], window: null },
  ],
}

function summaries(container: HTMLElement): string[] {
  return within(container)
    .getAllByTestId('rule-summary')
    .map((summary) => summary.textContent ?? '')
}

describe('GET /users/{id}/channel-preferences on /me/notifications', () => {
  test('the user sees their rules as editable rows with the fallback', async () => {
    server.use(respond(getUserChannelPreferences, 'get', getUrl, 200, anna))

    const { findAllByTestId, container, getByText, getByRole } = openAs(me, PATH)
    await findAllByTestId('rule-summary')

    expect(summaries(container)).toEqual([
      'Critical and above: SMS, every day 08:00 to 20:00',
      'Critical and above: Email, at any time',
    ])
    expect(getByText('Anything else: UI only')).toBeInTheDocument()
    expect(getByRole('button', { name: 'Save preferences' })).toBeDisabled()
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(http.get(getUrl, () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole } = openAs(me, PATH)

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('403 says only the user can change them', async () => {
    server.use(respond(getUserChannelPreferences, 'get', getUrl, 403, { detail: 'Not allowed.' }))

    const { findByRole } = openAs(me, PATH)

    expect(await findByRole('alert')).toHaveTextContent('You can only change your own notifications.')
  })
})

describe('PUT /users/{id}/channel-preferences on /me/notifications', () => {
  test('saving sends the rules in their new order, then shows them as saved', async () => {
    const reordered: ChannelPreferences = { rules: [...(anna.rules ?? [])].reverse() }
    server.use(
      respond(getUserChannelPreferences, 'get', getUrl, 200, anna),
      respond(setUserChannelPreferences, 'put', putUrl, 200, reordered),
    )
    const sent = recordRequests('put', putUrl)

    const { findByRole, getByRole, container, user } = openAs(me, PATH)
    await user.click(await findByRole('button', { name: 'Move rule 2 up' }))
    await user.click(getByRole('button', { name: 'Save preferences' }))

    await waitFor(() => expect(sent).toHaveLength(1))
    await waitFor(() =>
      expect(sent[0]?.body).toMatchObject({
        rules: [
          { min_severity: 'critical', channels: ['email'] },
          { min_severity: 'critical', channels: ['sms'] },
        ],
      }),
    )
    await waitFor(() => expect(getByRole('button', { name: 'Save preferences' })).toBeDisabled())
    expect(summaries(container)[0]).toBe('Critical and above: Email, at any time')
  })

  test('403 on save shows the reason and keeps the edits', async () => {
    server.use(
      respond(getUserChannelPreferences, 'get', getUrl, 200, anna),
      respond(setUserChannelPreferences, 'put', putUrl, 403, { detail: 'Not allowed.' }),
    )

    const { findByRole, getByRole, findByText, user } = openAs(me, PATH)
    await user.click(await findByRole('button', { name: 'Move rule 2 up' }))
    await user.click(getByRole('button', { name: 'Save preferences' }))

    expect(await findByText('You can only change your own notifications.')).toBeInTheDocument()
    expect(getByRole('button', { name: 'Save preferences' })).toBeEnabled()
  })
})
