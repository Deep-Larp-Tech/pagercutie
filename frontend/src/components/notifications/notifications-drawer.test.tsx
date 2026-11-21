import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, test } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import { getListDeliveriesUrl, listDeliveries } from '@/api/generated/alerts/alerts'
import { getGetMeUrl, getMe } from '@/api/generated/auth/auth'
import type { DeliveryRead } from '@/api/generated/model'
import { quietFeedEndpoints } from '@/test/alerts'
import { respond } from '@/test/http'
import { petra } from '@/test/people'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'
import { DELIVERIES_POLL_MS, deliveriesPollInterval } from './deliveries-query'
import { DRAWER_OPEN_KEY } from './use-drawer-open'

const me = petra('user', [])
const deliveriesUrl = getListDeliveriesUrl()

function delivery(overrides: Partial<DeliveryRead> & Pick<DeliveryRead, 'id' | 'channel' | 'created_at'>): DeliveryRead {
  return {
    alert_id: '0193a000-0000-7000-8000-0000000000a1',
    user_id: me.user.id,
    status: 'sent',
    attempts: 1,
    last_error: null,
    message: 'Settlement wf-8f21 failed at reserve-funds',
    sent_at: overrides.created_at,
    ...overrides,
  }
}

const sms = delivery({ id: 'd-sms', channel: 'sms', created_at: '2026-11-21T10:00:00Z' })
const email = delivery({
  id: 'd-email',
  channel: 'email',
  created_at: '2026-11-21T10:05:00Z',
  user_id: '0193a000-0000-7000-8000-0000000000b2',
  message: 'Rejected USD 12,400,000',
})
const failedCall = delivery({
  id: 'd-call',
  channel: 'phone',
  created_at: '2026-11-21T09:00:00Z',
  status: 'failed',
  attempts: 3,
  sent_at: null,
  last_error: 'Gateway timeout',
})

function signedIn(route = '/') {
  server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
  return renderApp(route)
}

/** Query strings of every `GET /deliveries` the test sends. */
function recordDeliveryQueries(): string[] {
  const queries: string[] = []
  server.events.on('request:start', ({ request }) => {
    const url = new URL(request.url)
    if (url.pathname === deliveriesUrl) queries.push(url.search)
  })
  return queries
}

beforeEach(() => server.use(...quietFeedEndpoints()))
afterEach(() => {
  localStorage.clear()
  server.events.removeAllListeners()
})

describe('notifications drawer', () => {
  test('the header button opens it, remembers it, and closes it again', async () => {
    server.use(respond(listDeliveries, 'get', deliveriesUrl, 200, []))
    const { findByRole, queryByRole, user } = signedIn()

    const toggle = await findByRole('button', { name: 'Sent notifications' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)

    expect(await findByRole('complementary', { name: 'Sent notifications' })).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(localStorage.getItem(DRAWER_OPEN_KEY)).toBe('open')

    await user.click(toggle)
    await waitFor(() => expect(queryByRole('complementary', { name: 'Sent notifications' })).not.toBeInTheDocument())
    expect(localStorage.getItem(DRAWER_OPEN_KEY)).toBeNull()
  })

  test('opens on load when it was open before', async () => {
    localStorage.setItem(DRAWER_OPEN_KEY, 'open')
    server.use(respond(listDeliveries, 'get', deliveriesUrl, 200, []))

    const { findByRole } = signedIn()

    expect(await findByRole('complementary', { name: 'Sent notifications' })).toBeInTheDocument()
  })

  test('Escape inside it closes it', async () => {
    localStorage.setItem(DRAWER_OPEN_KEY, 'open')
    server.use(respond(listDeliveries, 'get', deliveriesUrl, 200, []))
    const { findByRole, queryByRole, user } = signedIn()

    await user.click(within(await findByRole('complementary', { name: 'Sent notifications' })).getByRole('button', { name: 'SMS' }))
    await user.keyboard('{Escape}')

    await waitFor(() => expect(queryByRole('complementary', { name: 'Sent notifications' })).not.toBeInTheDocument())
  })
})

describe('GET /deliveries in the drawer', () => {
  test('lists every channel newest first, with recipient, status and the failure reason', async () => {
    localStorage.setItem(DRAWER_OPEN_KEY, 'open')
    server.use(respond(listDeliveries, 'get', deliveriesUrl, 200, [sms, failedCall, email]))

    const { findByRole } = signedIn()
    const list = await findByRole('list', { name: 'Deliveries, newest first' })
    const items = within(list).getAllByRole('listitem')

    expect(items.map((item) => within(item).getByRole('heading').textContent)).toEqual(['Email', 'SMS', 'Phone call'])
    expect(items[0]).toHaveTextContent('To user 0193a000')
    expect(items[1]).toHaveTextContent('To you')
    expect(items[2]).toHaveTextContent('Gateway timeout')
    expect(items[2]).toHaveTextContent(/3 attempts/)
  })

  test('a channel filter asks for that channel only', async () => {
    localStorage.setItem(DRAWER_OPEN_KEY, 'open')
    server.use(respond(listDeliveries, 'get', deliveriesUrl, 200, [sms]))
    const queries = recordDeliveryQueries()

    const { findByRole, user } = signedIn()
    const drawer = await findByRole('complementary', { name: 'Sent notifications' })
    await within(drawer).findByRole('list', { name: 'Deliveries, newest first' })
    await user.click(within(drawer).getByRole('button', { name: 'SMS' }))

    await waitFor(() => expect(queries.some((query) => new URLSearchParams(query).getAll('channel').join() === 'sms')).toBe(true))
    expect(new URLSearchParams(queries[0]).getAll('channel')).toEqual([])
  })

  test('shows an empty state when nothing was sent', async () => {
    localStorage.setItem(DRAWER_OPEN_KEY, 'open')
    server.use(respond(listDeliveries, 'get', deliveriesUrl, 200, []))

    const { findByText } = signedIn()

    expect(await findByText('Nothing sent yet')).toBeInTheDocument()
  })

  test('the 501 stub shows the shared fallback', async () => {
    localStorage.setItem(DRAWER_OPEN_KEY, 'open')
    server.use(http.get(deliveriesUrl, () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole } = signedIn()
    const drawer = await findByRole('complementary', { name: 'Sent notifications' })

    expect(await within(drawer).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('polls only while the endpoint answers 200', () => {
    expect(deliveriesPollInterval(200)).toBe(DELIVERIES_POLL_MS)
    expect(deliveriesPollInterval(501)).toBe(false)
    expect(deliveriesPollInterval(undefined)).toBe(false)
  })
})
