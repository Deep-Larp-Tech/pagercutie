import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import { getListMyMessagesQueryKey, getListMyMessagesUrl, listMyMessages } from '@/api/generated/alerts/alerts'
import { getGetMeUrl, getMe } from '@/api/generated/auth/auth'
import type { DeliveryRead } from '@/api/generated/model'
import { MESSAGES_POLL_MS } from '@/components/phone/messages-query'
import { respond } from '@/test/http'
import { petra } from '@/test/people'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const me = petra('user', [])

/** A delivery to Petra; times are UTC, so 13:02Z reads 14:02 in her Europe/Prague time zone. */
function delivery(id: string, overrides: Partial<DeliveryRead>): DeliveryRead {
  return {
    id,
    alert_id: '0193a000-0000-7000-8000-0000000000a1',
    user_id: me.user.id,
    channel: 'sms',
    status: 'sent',
    attempts: 1,
    last_error: null,
    message: `Message ${id}`,
    created_at: '2026-11-20T13:00:00Z',
    sent_at: '2026-11-20T13:00:05Z',
    ...overrides,
  }
}

function openPhone(route = '/me/phone') {
  server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
  return renderApp(route)
}

/** Answers `GET /me/messages` with `messages` and records each request's `channel` params. */
function serveMessages(messages: DeliveryRead[]) {
  const channels: string[][] = []
  server.use(
    http.get(getListMyMessagesUrl(), ({ request }) => {
      channels.push(new URL(request.url).searchParams.getAll('channel'))
      return HttpResponse.json(messages)
    }),
  )
  return channels
}

describe('GET /me/messages', () => {
  test('lists SMS and calls newest first inside the simulated phone', async () => {
    serveMessages([
      delivery('older', { created_at: '2026-11-20T08:00:00Z', message: 'Settlement wf-1 failed' }),
      delivery('newest', { created_at: '2026-11-20T13:02:00Z', channel: 'phone', message: 'Critical alert call' }),
      delivery('middle', { created_at: '2026-11-20T10:00:00Z', message: 'Payments slow' }),
    ])
    const { findByRole } = openPhone()

    const phone = await findByRole('region', { name: 'Simulated phone' })
    const list = await within(phone).findByRole('list', { name: 'Messages, newest first' })
    const items = within(list).getAllByRole('listitem')

    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('Critical alert call'),
      expect.stringContaining('Payments slow'),
      expect.stringContaining('Settlement wf-1 failed'),
    ])
    expect(within(items[0]).getByRole('heading', { name: 'Phone call' })).toBeInTheDocument()
    expect(within(items[1]).getByRole('heading', { name: 'SMS' })).toBeInTheDocument()
  })

  test('the channel filter maps to the channel query parameter and the URL', async () => {
    const channels = serveMessages([])
    const { findByRole, router, user } = openPhone()

    const filter = await findByRole('group', { name: 'Channel' })
    await waitFor(() => expect(channels).toEqual([['sms', 'phone']]))

    await user.click(within(filter).getByRole('button', { name: 'SMS' }))
    await waitFor(() => expect(channels.at(-1)).toEqual(['sms']))
    expect(router.state.location.search).toEqual({ channel: 'sms' })

    await user.click(within(filter).getByRole('button', { name: 'Calls' }))
    await waitFor(() => expect(channels.at(-1)).toEqual(['phone']))
    expect(await findByRole('heading', { name: 'No calls yet' })).toBeInTheDocument()
  })

  test('opening /me/phone?channel=phone asks for calls only', async () => {
    const channels = serveMessages([])
    const { findByRole } = openPhone('/me/phone?channel=phone')

    const filter = await findByRole('group', { name: 'Channel' })
    expect(within(filter).getByRole('button', { name: 'Calls' })).toHaveAttribute('aria-pressed', 'true')
    await waitFor(() => expect(channels).toEqual([['phone']]))
  })

  test('each delivery status shows an icon and words', async () => {
    serveMessages([
      delivery('pending', { status: 'pending', sent_at: null, created_at: '2026-11-20T13:03:00Z' }),
      delivery('sent', { status: 'sent', channel: 'phone', sent_at: '2026-11-20T13:02:00Z', created_at: '2026-11-20T13:02:00Z' }),
      delivery('failed', { status: 'failed', attempts: 3, sent_at: null, last_error: 'gateway down', created_at: '2026-11-20T13:01:00Z' }),
    ])
    const { findAllByRole } = openPhone()

    const [pending, sent, failed] = await findAllByRole('listitem')

    expect(within(pending).getByText('Sending by SMS')).toBeInTheDocument()
    expect(pending.querySelector('svg.lucide-clock')).not.toBeNull()
    expect(within(sent).getByText(/^Sent by phone call/)).toHaveTextContent(/^Sent by phone call, 20 Nov( 2026)?, 14:02$/)
    expect(sent.querySelector('svg.lucide-check')).not.toBeNull()
    expect(within(failed).getByText('SMS failed, retrying. 3 attempts so far')).toBeInTheDocument()
    expect(failed.querySelector('svg.lucide-circle-x')).not.toBeNull()
  })

  test('shows the time in Geist Mono with the full date in a tooltip', async () => {
    serveMessages([delivery('one', { created_at: '2026-11-20T13:02:00Z' })])
    const { findByText, user } = openPhone()

    const time = await findByText(/14:02$/, { selector: 'time' })
    expect(time).toHaveClass('font-mono')
    expect(time).toHaveAttribute('dateTime', '2026-11-20T13:02:00Z')

    await user.hover(time)
    expect(await findByText('Friday, 20 November 2026 at 14:02:00 CET')).toBeInTheDocument()
  })

  test('an empty list says what will show up', async () => {
    serveMessages([])
    const { findByRole, findByText } = openPhone()

    expect(await findByRole('heading', { name: 'No messages yet' })).toBeInTheDocument()
    expect(await findByText('SMS and calls sent to you show up here.')).toBeInTheDocument()
  })

  test('shows a skeleton while loading', async () => {
    let answer: () => void = () => {}
    const answered = new Promise<void>((resolve) => {
      answer = resolve
    })
    server.use(
      http.get(getListMyMessagesUrl(), async () => {
        await answered
        return HttpResponse.json([])
      }),
    )
    const { findByTestId, findByRole } = openPhone()

    expect(await findByTestId('messages-skeleton')).toBeInTheDocument()
    answer()
    expect(await findByRole('heading', { name: 'No messages yet' })).toBeInTheDocument()
  })

  test('422 shows an error with a retry', async () => {
    server.use(
      respond(listMyMessages, 'get', getListMyMessagesUrl(), 422, {
        detail: [{ loc: ['query', 'channel', 0], msg: 'Input should be sms', type: 'enum' }],
      }),
    )
    const { findByRole } = openPhone()

    const alert = await findByRole('alert')
    expect(alert).toHaveTextContent("Couldn't load your messages")
    expect(alert).toHaveTextContent('Reload the page and try again.')
    expect(await findByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  test('an undocumented status such as the 501 stub falls back to the shared message', async () => {
    server.use(http.get(getListMyMessagesUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const { findByRole } = openPhone()

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('a network error says to check the connection, and Try again reloads', { timeout: 10_000 }, async () => {
    let fail = true
    server.use(
      http.get(getListMyMessagesUrl(), () => (fail ? HttpResponse.error() : HttpResponse.json([]))),
    )
    const { findByRole, user } = openPhone()

    // The QueryClient retries network errors twice (1 s, then 2 s) before the error shows.
    expect(await findByRole('alert', {}, { timeout: 5000 })).toHaveTextContent('Check your connection and try again.')
    fail = false
    await user.click(await findByRole('button', { name: 'Try again' }))
    expect(await findByRole('heading', { name: 'No messages yet' })).toBeInTheDocument()
  })

  test('polls every 10 s while it answers 200, and not while the tab is hidden', async () => {
    serveMessages([])
    const { findByRole, queryClient } = openPhone()
    await findByRole('heading', { name: 'No messages yet' })

    const query = queryClient.getQueryCache().find({ queryKey: getListMyMessagesQueryKey({ channel: ['sms', 'phone'] }) })
    const options = query?.observers[0]?.options
    expect(options?.refetchIntervalInBackground).toBe(false)
    const interval = options?.refetchInterval
    expect(typeof interval === 'function' && query !== undefined ? interval(query) : interval).toBe(MESSAGES_POLL_MS)
  })
})
