import { http, HttpResponse, delay } from 'msw'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { act, waitFor, within } from '@testing-library/react'
import {
  acknowledgeAlert,
  getAcknowledgeAlertUrl,
  getListAlertsUrl,
  getResolveAlertUrl,
  listAlerts,
  resolveAlert,
} from '@/api/generated/alerts/alerts'
import type { AlertRead, MeRead, TeamRole } from '@/api/generated/model'
import { Toaster } from '@/components/ui/sonner'
import { OFFLINE_AFTER_MS, reconnectDelay } from '@/hooks/use-alert-stream'
import type { AlertFilters } from '@/lib/alert-feed'
import { RESOLVE_EXIT_MS } from '@/lib/motion'
import { alert, uuidTeam } from '@/test/alerts'
import { FakeEventSource } from '@/test/event-source'
import { respond } from '@/test/http'
import { membership, petra } from '@/test/people'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { LiveAlertFeed } from './live-alert-feed'

const settlements = uuidTeam('settlements', 'Settlements')
const openOnly: AlertFilters = { status: ['open', 'acknowledged'] }

function asRole(role: TeamRole): MeRead {
  return petra('user', [membership(settlements, role)])
}

function renderFeed(me: MeRead, filters: AlertFilters = openOnly) {
  return renderWithProviders(
    <>
      <LiveAlertFeed
        teamId={settlements.id}
        filters={filters}
        empty={{ title: 'No open alerts', description: 'Alerts show up here.' }}
      />
      <Toaster />
    </>,
    { me },
  )
}

function listing(alerts: AlertRead[]) {
  return respond(listAlerts, 'get', getListAlertsUrl(), 200, alerts)
}

/** Opens the stream and waits for the reload every (re)connect triggers. */
async function connect(requests: { count: number }) {
  const before = requests.count
  // The router renders the feed after it resolves the route, so the connection may not exist yet.
  const source = await waitFor(() => FakeEventSource.latest())
  act(() => source.open())
  await waitFor(() => expect(requests.count).toBeGreaterThan(before))
}

function countingListing(alerts: AlertRead[]) {
  const requests = { count: 0 }
  server.use(
    http.get(getListAlertsUrl(), () => {
      requests.count += 1
      return HttpResponse.json(alerts)
    }),
  )
  return requests
}

afterEach(() => {
  vi.useRealTimers()
})

describe('GET /alerts', () => {
  test('shows three skeleton cards while loading', async () => {
    server.use(http.get(getListAlertsUrl(), async () => delay('infinite')))

    const { findByRole } = renderFeed(asRole('member'))

    const loading = await findByRole('status', { name: 'Loading alerts' })
    expect(loading.children).toHaveLength(3)
  })

  test('renders each alert with severity, status, counter and fields in Geist Mono', async () => {
    const item = alert(settlements.id, { occurrences: 12 })
    server.use(listing([item]))

    const { findByRole, getByText } = renderFeed(asRole('member'))

    const card = await findByRole('article', { name: item.title })
    expect(within(card).getByText('Critical')).toBeInTheDocument()
    expect(within(card).getByText('Open')).toBeInTheDocument()
    expect(within(card).getByLabelText('12 occurrences')).toHaveTextContent('×12')
    expect(getByText('payload.workflowId')).toHaveClass('text-muted-foreground')
    expect(within(card).getByText('12,400,000').closest('dl')).toHaveClass('font-mono')
  })

  test('sends the team and the filters as query parameters', async () => {
    let query: URLSearchParams | undefined
    server.use(
      http.get(getListAlertsUrl(), ({ request }) => {
        query = new URL(request.url).searchParams
        return HttpResponse.json([])
      }),
    )

    const { findByText } = renderFeed(asRole('member'), { status: ['open'], severity: ['critical', 'error'] })

    expect(await findByText('No open alerts')).toBeInTheDocument()
    expect(query?.get('team_id')).toBe(settlements.id)
    expect(query?.getAll('status')).toEqual(['open'])
    expect(query?.getAll('severity')).toEqual(['critical', 'error'])
  })

  test('an empty list shows the empty state', async () => {
    server.use(listing([]))

    const { findByText } = renderFeed(asRole('member'))

    expect(await findByText('No open alerts')).toBeInTheDocument()
  })

  test('422 says the filters are invalid', async () => {
    server.use(respond(listAlerts, 'get', getListAlertsUrl(), 422, { detail: [] }))

    const { findByRole } = renderFeed(asRole('member'))

    expect(await findByRole('alert')).toHaveTextContent(
      "Couldn't load alerts" + "The filters in the address aren't valid. Clear them and try again.",
    )
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(http.get(getListAlertsUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole } = renderFeed(asRole('member'))

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('GET /alerts/stream', () => {
  test('connects to the team stream and adds a new alert without reloading the page', async () => {
    const requests = countingListing([])
    const { findByText, findByRole, getByTestId } = renderFeed(asRole('member'))
    expect(await findByText('No open alerts')).toBeInTheDocument()
    expect(FakeEventSource.latest().url).toBe(`/api/alerts/stream?team_id=${settlements.id}`)
    await connect(requests)

    const fired = alert(settlements.id)
    act(() => FakeEventSource.latest().send({ type: 'alert.created', alert: fired }))

    expect(await findByRole('article', { name: fired.title })).toBeInTheDocument()
    expect(getByTestId('announcer-assertive')).toHaveTextContent(`Critical: ${fired.title}`)
    expect(getByTestId('announcer-polite')).toBeEmptyDOMElement()
  })

  test('announces a new info alert politely', async () => {
    const requests = countingListing([])
    const { findByRole, getByTestId } = renderFeed(asRole('member'))
    await connect(requests)

    const fired = alert(settlements.id, { severity: 'info', colour: 'blue', title: 'Nightly export finished late' })
    act(() => FakeEventSource.latest().send({ type: 'alert.created', alert: fired }))

    expect(await findByRole('article', { name: fired.title })).toBeInTheDocument()
    expect(getByTestId('announcer-polite')).toHaveTextContent('Info: Nightly export finished late')
    expect(getByTestId('announcer-assertive')).toBeEmptyDOMElement()
  })

  test('a repeat occurrence bumps the counter and flashes the card without announcing', async () => {
    const item = alert(settlements.id, { occurrences: 3 })
    const requests = countingListing([item])
    const { findByLabelText, getByTestId, queryByTestId } = renderFeed(asRole('member'))
    expect(await findByLabelText('3 occurrences')).toBeInTheDocument()
    await connect(requests)
    expect(queryByTestId('repeat-flash')).not.toBeInTheDocument()

    act(() =>
      FakeEventSource.latest().send({
        type: 'alert.updated',
        alert: { ...item, occurrences: 4, last_seen_at: '2026-11-21T12:05:00Z' },
      }),
    )

    expect(await findByLabelText('4 occurrences')).toHaveTextContent('×4')
    expect(getByTestId('repeat-flash')).toBeInTheDocument()
    expect(getByTestId('announcer-polite')).toBeEmptyDOMElement()
    expect(getByTestId('announcer-assertive')).toBeEmptyDOMElement()
  })

  test('a message that is not a valid event is ignored', async () => {
    const requests = countingListing([])
    const { findByText } = renderFeed(asRole('member'))
    await connect(requests)

    act(() => FakeEventSource.latest().send({ raw: '{"type":"alert.created","alert":{"id":"x"}}' }))

    expect(await findByText('No open alerts')).toBeInTheDocument()
  })

  test('an alert resolved elsewhere shows as resolved, then leaves the open feed after 700 ms', async () => {
    const item = alert(settlements.id)
    const requests = countingListing([item])
    const { findByRole, queryByRole } = renderFeed(asRole('member'))
    const card = await findByRole('article', { name: item.title })
    await connect(requests)

    act(() =>
      FakeEventSource.latest().send({
        type: 'alert.updated',
        alert: { ...item, status: 'resolved', resolution: 'auto', resolved_at: '2026-11-21T12:10:00Z' },
      }),
    )

    expect(await within(card).findByText('Resolved automatically')).toBeInTheDocument()
    await waitFor(() => expect(queryByRole('article', { name: item.title })).not.toBeInTheDocument(), {
      timeout: RESOLVE_EXIT_MS + 1000,
    })
  })

  test('a dropped connection shows Reconnecting, then pauses after 10 s, and Retry reconnects and reloads', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const requests = countingListing([])
    const { findByText, findByRole, queryByRole } = renderFeed(asRole('member'))
    expect(await findByText('No open alerts')).toBeInTheDocument()
    expect(queryByRole('status')).not.toBeInTheDocument()

    act(() => FakeEventSource.latest().fail())
    expect(await findByRole('status')).toHaveTextContent('Reconnecting…')
    expect(FakeEventSource.latest().closed).toBe(true)

    await act(() => vi.advanceTimersByTimeAsync(reconnectDelay(0)))
    expect(FakeEventSource.instances).toHaveLength(2)
    act(() => FakeEventSource.latest().fail())

    await act(() => vi.advanceTimersByTimeAsync(OFFLINE_AFTER_MS))
    const bar = await findByRole('status')
    expect(bar).toHaveTextContent('Live updates paused')

    const opened = FakeEventSource.instances.length
    act(() => within(bar).getByRole('button', { name: 'Retry' }).click())
    expect(FakeEventSource.instances).toHaveLength(opened + 1)
    expect(await findByRole('status')).toHaveTextContent('Reconnecting…')

    await connect(requests)
    await waitFor(() => expect(queryByRole('status')).not.toBeInTheDocument())
  })

  test('every reconnect reloads the list and keeps the events that arrived meanwhile', async () => {
    const first = alert(settlements.id, { title: 'Settlement wf-1 failed' })
    const missed = alert(settlements.id, { title: 'Settlement wf-2 failed', last_seen_at: '2026-11-21T12:20:00Z' })
    const alerts = [first]
    const requests = { count: 0 }
    server.use(
      http.get(getListAlertsUrl(), () => {
        requests.count += 1
        return HttpResponse.json(alerts)
      }),
    )
    const { findByRole } = renderFeed(asRole('member'))
    await connect(requests)
    act(() => FakeEventSource.latest().fail())

    // The alert fired while the stream was down; the reload after the next open brings it in.
    alerts.push(missed)
    await act(() => new Promise((resolve) => setTimeout(resolve, reconnectDelay(0))))
    await connect(requests)

    expect(await findByRole('article', { name: missed.title })).toBeInTheDocument()
    expect(await findByRole('article', { name: first.title })).toBeInTheDocument()
  })
})

describe('POST /alerts/{id}/acknowledge', () => {
  test('acknowledges at once, then confirms with a toast', async () => {
    const item = alert(settlements.id)
    const me = asRole('member')
    let release = () => {}
    const answered = new Promise<void>((resolve) => {
      release = resolve
    })
    const saved: AlertRead = {
      ...item,
      status: 'acknowledged',
      acknowledged_by: me.user.id,
      acknowledged_at: '2026-11-21T12:01:00Z',
    }
    server.use(
      listing([item]),
      http.post(getAcknowledgeAlertUrl(item.id), async () => {
        await answered
        return HttpResponse.json(saved)
      }),
    )
    const { findByRole, user, findByText } = renderFeed(me)
    const card = await findByRole('article', { name: item.title })

    await user.click(within(card).getByRole('button', { name: 'Acknowledge' }))

    expect(within(card).getByText("You're on it")).toBeInTheDocument()
    expect(await within(card).findByRole('button', { name: 'Resolve' })).toBeInTheDocument()
    release()
    expect(await findByText('Alert acknowledged')).toBeInTheDocument()
  })

  test('409 puts the alert back and says why', async () => {
    const item = alert(settlements.id)
    server.use(
      listing([item]),
      respond(acknowledgeAlert, 'post', getAcknowledgeAlertUrl(item.id), 409, { detail: 'Alert is not open' }),
    )
    const { findByRole, user } = renderFeed(asRole('lead'))
    const card = await findByRole('article', { name: item.title })

    await user.click(within(card).getByRole('button', { name: 'Acknowledge' }))

    expect(await within(card).findByRole('alert')).toHaveTextContent(
      'Someone else changed this alert first. The feed now shows its current state.',
    )
    expect(await within(card).findByRole('button', { name: 'Acknowledge' })).toBeInTheDocument()
    expect(within(card).getByText('Open')).toBeInTheDocument()
  })

  test('a network failure puts the alert back', async () => {
    const item = alert(settlements.id)
    server.use(listing([item]), http.post(getAcknowledgeAlertUrl(item.id), () => HttpResponse.error()))
    const { findByRole, user } = renderFeed(asRole('member'))
    const card = await findByRole('article', { name: item.title })

    await user.click(within(card).getByRole('button', { name: 'Acknowledge' }))

    expect(await within(card).findByRole('alert')).toHaveTextContent(
      "Couldn't reach the server. Check your connection and try again.",
    )
    expect(within(card).getByText('Open')).toBeInTheDocument()
  })

  test('a viewer sees no Acknowledge or Resolve buttons', async () => {
    const open = alert(settlements.id, { title: 'Open one' })
    const acknowledged = alert(settlements.id, { title: 'Acknowledged one', status: 'acknowledged' })
    server.use(listing([open, acknowledged]))

    const { findByRole, queryByRole } = renderFeed(asRole('viewer'))

    expect(await findByRole('article', { name: 'Open one' })).toBeInTheDocument()
    expect(queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
    expect(queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument()
  })
})

describe('POST /alerts/{id}/resolve', () => {
  test('resolves at once, confirms with a toast and leaves the open feed after 700 ms', async () => {
    const me = asRole('member')
    const item = alert(settlements.id, { status: 'acknowledged', acknowledged_by: me.user.id })
    const saved: AlertRead = {
      ...item,
      status: 'resolved',
      resolution: 'manual',
      resolved_by: me.user.id,
      resolved_at: '2026-11-21T12:02:00Z',
    }
    server.use(listing([item]), respond(resolveAlert, 'post', getResolveAlertUrl(item.id), 200, saved))
    const { findByRole, findByText, queryByRole, user } = renderFeed(me)
    const card = await findByRole('article', { name: item.title })
    expect(within(card).getByText("You're on it")).toBeInTheDocument()

    await user.click(within(card).getByRole('button', { name: 'Resolve' }))

    expect(within(card).getByText('Resolved')).toBeInTheDocument()
    expect(await findByText('Alert resolved')).toBeInTheDocument()
    await waitFor(() => expect(queryByRole('article', { name: item.title })).not.toBeInTheDocument(), {
      timeout: RESOLVE_EXIT_MS + 1000,
    })
  })

  test('409 puts the alert back and says why', async () => {
    const item = alert(settlements.id, { status: 'acknowledged' })
    server.use(
      listing([item]),
      respond(resolveAlert, 'post', getResolveAlertUrl(item.id), 409, { detail: 'Already resolved' }),
    )
    const { findByRole, user } = renderFeed(asRole('member'))
    const card = await findByRole('article', { name: item.title })

    await user.click(within(card).getByRole('button', { name: 'Resolve' }))

    expect(await within(card).findByRole('alert')).toHaveTextContent('Someone else changed this alert first.')
    expect(within(card).getByRole('button', { name: 'Resolve' })).toBeInTheDocument()
    expect(within(card).getByText('Someone is on it')).toBeInTheDocument()
  })

  test('403 puts the alert back and names the role needed', async () => {
    const item = alert(settlements.id, { status: 'acknowledged' })
    server.use(
      listing([item]),
      respond(resolveAlert, 'post', getResolveAlertUrl(item.id), 403, { detail: 'Forbidden' }),
    )
    const { findByRole, user } = renderFeed(asRole('member'))
    const card = await findByRole('article', { name: item.title })

    await user.click(within(card).getByRole('button', { name: 'Resolve' }))

    expect(await within(card).findByRole('alert')).toHaveTextContent(
      "You can't respond to this alert. Ask a team lead for the member role.",
    )
  })
})
