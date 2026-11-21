import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import type { ChannelPreferences, ChannelRule } from '@/api/generated/model'
import {
  getGetTeamChannelPreferencesUrl,
  getSetTeamChannelPreferencesUrl,
  getTeamChannelPreferences,
  setTeamChannelPreferences,
} from '@/api/generated/teams/teams'
import { respond } from '@/test/http'
import { server } from '@/test/server'
import { openAs, petraIn, recordRequests, settlements } from '@/test/teams'

const PATH = '/teams/settlements/settings/notifications'
const getUrl = getGetTeamChannelPreferencesUrl(settlements.id)
const putUrl = getSetTeamChannelPreferencesUrl(settlements.id)

const daytimeSms: ChannelRule = {
  min_severity: 'critical',
  channels: ['sms'],
  window: { days: ['mon', 'tue', 'wed', 'thu', 'fri'], start: '08:00:00', end: '20:00:00' },
}
const emailErrors: ChannelRule = { min_severity: 'error', channels: ['email'], window: null }
const saved: ChannelPreferences = { rules: [daytimeSms, emailErrors] }

function withPreferences(preferences: ChannelPreferences = saved) {
  server.use(respond(getTeamChannelPreferences, 'get', getUrl, 200, preferences))
}

function summaries(container: HTMLElement): string[] {
  return within(container)
    .getAllByTestId('rule-summary')
    .map((summary) => summary.textContent ?? '')
}

describe('GET /teams/{id}/channel-preferences', () => {
  test('a lead sees each rule as an editable row with its plain-language preview and the fallback', async () => {
    withPreferences()

    const { findAllByTestId, container, getByText, getByRole } = openAs(petraIn('lead'), PATH)
    await findAllByTestId('rule-summary')

    expect(summaries(container)).toEqual([
      'Critical and above: SMS, weekdays 08:00 to 20:00',
      'Error and above: Email, at any time',
    ])
    expect(getByText('Anything else: UI only')).toBeInTheDocument()
    expect(getByRole('group', { name: 'Channels for rule 1' })).toBeInTheDocument()
    expect(getByRole('button', { name: 'Save preferences' })).toBeDisabled()
  })

  test('a member reads the rules as sentences without controls', async () => {
    withPreferences()

    const { findByRole, getByText, queryByRole } = openAs(petraIn('member'), PATH)
    const list = await findByRole('list')

    expect(within(list).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Critical and above: SMS, weekdays 08:00 to 20:00',
      'Error and above: Email, at any time',
    ])
    expect(getByText('Anything else: UI only')).toBeInTheDocument()
    expect(getByText('Only team leads can change this.')).toBeInTheDocument()
    expect(queryByRole('button', { name: /Save preferences|Add rule/ })).not.toBeInTheDocument()
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(http.get(getUrl, () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole } = openAs(petraIn('lead'), PATH)

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('an undocumented 403 shows the shared fallback', async () => {
    server.use(http.get(getUrl, () => HttpResponse.json({ detail: 'x' }, { status: 403 })))

    const { findByRole } = openAs(petraIn('lead'), PATH)

    expect(await findByRole('alert')).toHaveTextContent('Something went wrong on the server (HTTP 403).')
  })
})

describe('editing rules', () => {
  test('a new rule previews as it is edited, with a window that crosses midnight', async () => {
    withPreferences({ rules: [] })

    const { findByRole, getByRole, getByLabelText, container, user } = openAs(petraIn('lead'), PATH)
    await user.click(await findByRole('button', { name: 'Add rule' }))
    expect(summaries(container)).toEqual(['Critical and above: Email, at any time'])

    await user.click(getByRole('button', { name: 'SMS' }))
    await user.click(getByRole('switch'))
    expect(summaries(container)).toEqual(['Critical and above: Email, SMS, weekdays 08:00 to 20:00'])

    const days = getByRole('group', { name: 'Days for rule 1' })
    await user.click(within(days).getByRole('button', { name: 'Sat' }))
    await user.click(within(days).getByRole('button', { name: 'Sun' }))
    await user.clear(getByLabelText('From'))
    await user.type(getByLabelText('From'), '22:00')
    await user.clear(getByLabelText('To'))
    await user.type(getByLabelText('To'), '06:00')

    expect(summaries(container)).toEqual(['Critical and above: Email, SMS, every day 22:00 to 06:00 the next day'])
  })

  test('moving a rule up changes the order', async () => {
    withPreferences()

    const { findByRole, container, user } = openAs(petraIn('lead'), PATH)
    await user.click(await findByRole('button', { name: 'Move rule 2 up' }))

    expect(summaries(container)).toEqual([
      'Error and above: Email, at any time',
      'Critical and above: SMS, weekdays 08:00 to 20:00',
    ])
  })

  test('twenty rules is the most; Add rule turns off and says why', async () => {
    withPreferences({ rules: Array.from({ length: 20 }, () => emailErrors) })

    const { findByRole, getByText } = openAs(petraIn('lead'), PATH)

    expect(await findByRole('button', { name: 'Add rule' })).toBeDisabled()
    expect(getByText('You can add up to 20 rules.')).toBeInTheDocument()
  })

  test('an empty channel list is caught before sending', async () => {
    withPreferences()
    const puts = recordRequests('put', putUrl)

    const { findByRole, getByRole, findByText, user } = openAs(petraIn('lead'), PATH)
    const channels = await findByRole('group', { name: 'Channels for rule 2' })
    await user.click(within(channels).getByRole('button', { name: 'Email' }))
    await user.click(getByRole('button', { name: 'Save preferences' }))

    expect(await findByText('Pick at least one channel.')).toBeInTheDocument()
    expect(puts).toEqual([])
  })
})

describe('PUT /teams/{id}/channel-preferences', () => {
  test('200 sends the rules in order with HH:MM times and says so', async () => {
    withPreferences()
    server.use(respond(setTeamChannelPreferences, 'put', putUrl, 200, { rules: [emailErrors, daytimeSms] }))
    const puts = recordRequests('put', putUrl)

    const { findByRole, getByRole, findByText, user } = openAs(petraIn('lead'), PATH)
    await user.click(await findByRole('button', { name: 'Move rule 2 up' }))
    await user.click(getByRole('button', { name: 'Save preferences' }))

    expect(await findByText('Notification settings saved')).toBeInTheDocument()
    await waitFor(() =>
      expect(puts.map(({ body }) => body)).toEqual([
        {
          rules: [
            { min_severity: 'error', channels: ['email'], window: null },
            {
              min_severity: 'critical',
              channels: ['sms'],
              window: { days: ['mon', 'tue', 'wed', 'thu', 'fri'], start: '08:00', end: '20:00' },
            },
          ],
        },
      ]),
    )
  })

  test('422 for an empty channel list shows the message under that rule', async () => {
    withPreferences()
    server.use(
      respond(setTeamChannelPreferences, 'put', putUrl, 422, {
        detail: [{ loc: ['body', 'rules', 1, 'channels'], msg: 'List should have at least 1 item', type: 'too_short' }],
      }),
    )

    const { findByRole, getByRole, findByText, user } = openAs(petraIn('lead'), PATH)
    await user.click(await findByRole('button', { name: 'Move rule 2 up' }))
    await user.click(getByRole('button', { name: 'Save preferences' }))

    const error = await findByText('List should have at least 1 item')
    expect(error).toHaveAttribute('data-slot', 'field-error')
    expect(error.closest('li')).toHaveAccessibleName('Rule 2')
  })

  test('403 says only leads can change it', async () => {
    withPreferences()
    server.use(respond(setTeamChannelPreferences, 'put', putUrl, 403, { detail: 'Forbidden' }))

    const { findByRole, getByRole, user } = openAs(petraIn('lead'), PATH)
    await user.click(await findByRole('button', { name: 'Move rule 2 up' }))
    await user.click(getByRole('button', { name: 'Save preferences' }))

    expect(await findByRole('alert')).toHaveTextContent('Only team leads can change this.')
  })

  test('the 501 stub shows the shared fallback', async () => {
    withPreferences()
    server.use(http.put(putUrl, () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole, getByRole, user } = openAs(petraIn('lead'), PATH)
    await user.click(await findByRole('button', { name: 'Remove rule 1' }))
    await user.click(getByRole('button', { name: 'Save preferences' }))

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})
