import { delay, http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, onTestFinished, test } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import { getListAuditEntriesUrl, listAuditEntries } from '@/api/generated/audit/audit'
import type { AuditEntryRead, UserRead } from '@/api/generated/model'
import { getListTeamsUrl, listTeams } from '@/api/generated/teams/teams'
import { getListUsersUrl, listUsers } from '@/api/generated/users/users'
import { respond } from '@/test/http'
import { petra, team } from '@/test/people'
import { server } from '@/test/server'
import { openAs, petraIn, settlements } from '@/test/teams'
import { nth } from '@/test/elements'

const PATH = '/teams/settlements/audit'
const alertId = '0193c000-0000-7000-8000-00000000a1e7'
const otherUser = '0193a000-0000-7000-8000-0000000000b0'
const namedUser = '0193a000-0000-7000-8000-0000000000c0'
const ola: UserRead = {
  id: namedUser,
  email: 'ola@example.com',
  display_name: 'Ola Berg',
  phone: null,
  timezone: 'Europe/Oslo',
  role: 'user',
  created_at: '2026-01-01T00:00:00Z',
}

let sequence = 0

function entry(overrides: Partial<AuditEntryRead> = {}): AuditEntryRead {
  sequence += 1
  return {
    id: `0193d000-0000-7000-8000-${sequence.toString(16).padStart(12, '0')}`,
    at: '2026-11-21T12:00:00Z',
    actor_user_id: null,
    action: 'alert.acknowledged',
    entity_type: 'alert',
    entity_id: alertId,
    team_id: settlements.id,
    data: {},
    ...overrides,
  }
}

/** Query strings of every `GET /audit` the app sends during the test. */
function recordAuditQueries(): URLSearchParams[] {
  const queries: URLSearchParams[] = []
  const listener = ({ request }: { request: Request }) => {
    const url = new URL(request.url)
    if (url.pathname === getListAuditEntriesUrl()) queries.push(url.searchParams)
  }
  server.events.on('request:start', listener)
  onTestFinished(() => server.events.removeListener('request:start', listener))
  return queries
}

beforeEach(() => {
  server.use(respond(listTeams, 'get', getListTeamsUrl(), 200, [settlements]))
})

describe('GET /audit on the team audit log', () => {
  test('lists entries with who, what in plain words and the entity', async () => {
    const lead = petraIn('lead')
    server.use(
      respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [
        entry({ actor_user_id: lead.user.id, action: 'alert.acknowledged' }),
        entry({ actor_user_id: null, action: 'step.awaiting_approval', data: { step: 'reserve-funds' } }),
        entry({ actor_user_id: namedUser, actor_name: 'Ola Berg', action: 'rule.updated', entity_type: 'rule' }),
        entry({ actor_user_id: otherUser, action: 'rule.created', entity_type: 'rule' }),
      ]),
    )
    const { findByRole, getByRole, user } = openAs(lead, PATH)

    const table = await findByRole('table', { name: 'Audit log' })
    await within(table).findByText('Changed a rule')
    const rows = within(table).getAllByRole('row')
    expect(rows.slice(1).map((row) => within(row).getAllByRole('cell')[1]?.textContent)).toEqual([
      'You',
      'System',
      'Ola Berg',
      'User 0193a000',
    ])
    expect(within(table).getByText('Acknowledged the alert')).toBeInTheDocument()
    expect(within(table).getByText('A step is waiting for approval')).toBeInTheDocument()
    expect(within(table).getAllByRole('link', { name: 'Rule' })[0]).toHaveAttribute('href', '/teams/settlements/rules')
    expect(within(table).getAllByRole('link', { name: 'Alert' })[0]).toHaveAttribute(
      'href',
      '/teams/settlements/alerts',
    )

    await user.click(getByRole('button', { name: 'Show details of A step is waiting for approval' }))

    expect(within(table).getByText(/"step": "reserve-funds"/)).toBeInTheDocument()
    expect(getByRole('button', { name: 'Hide details of A step is waiting for approval' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  test('filters in the address go into the request and show in the controls', async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]))
    const queries = recordAuditQueries()
    const search = `entity_type=alert&entity_id=${alertId}&action=alert.resolved&actor_user_id=${otherUser}&range=24h`

    const { findByRole, getByLabelText, getByRole } = openAs(petraIn('viewer'), `${PATH}?${search}`)

    await findByRole('table', { name: 'Audit log' })
    const query = Object.fromEntries(queries.at(-1) ?? [])
    expect(query).toEqual({
      team_id: settlements.id,
      entity_type: 'alert',
      entity_id: alertId,
      action: 'alert.resolved',
      actor_user_id: otherUser,
      since: expect.stringMatching(/^\d{4}-\d\d-\d\dT/),
      limit: '100',
      offset: '0',
    })
    expect(Date.now() - Date.parse(query.since ?? '')).toBeLessThan(24 * 60 * 60_000 + 60_000)
    expect(getByLabelText('Entity type')).toHaveTextContent('Alert')
    expect(getByLabelText('Action')).toHaveTextContent('Resolved the alert')
    expect(getByRole('combobox', { name: 'Who' })).toHaveValue('User 0193a000')
    expect(getByRole('button', { name: 'Last 24 hours' })).toHaveAttribute('aria-pressed', 'true')
    expect(getByRole('button', { name: `Stop filtering by alert ${alertId}` })).toBeInTheDocument()
  })

  test('a team page has no team filter and offers no user entries', async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]))
    const { findByRole, getByLabelText, queryByLabelText, user } = openAs(petraIn('member'), PATH)
    await findByRole('table', { name: 'Audit log' })

    expect(queryByLabelText('Team')).not.toBeInTheDocument()
    await user.click(getByLabelText('Entity type'))
    const options = within(await findByRole('listbox')).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual([
      'All types',
      'Team',
      'Source',
      'Event schema',
      'Rule',
      'Runbook',
      'Alert',
    ])
  })

  test('picking an entity type applies at once and drops an action of another type', async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]))
    const queries = recordAuditQueries()
    const { findByRole, getByLabelText, user, router } = openAs(petraIn('member'), `${PATH}?action=alert.resolved`)
    await findByRole('table', { name: 'Audit log' })

    await user.click(getByLabelText('Entity type'))
    await user.click(await findByRole('option', { name: 'Rule' }))

    await waitFor(() => expect(router.state.location.search).toEqual({ entity_type: 'rule' }))
    await waitFor(() => expect(queries.at(-1)?.get('entity_type')).toBe('rule'))
    expect(queries.at(-1)?.has('action')).toBe(false)

    await user.click(getByLabelText('Action'))
    const listbox = await findByRole('listbox')
    expect(within(listbox).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'All actions',
      'Created a rule',
      'Changed a rule',
      'Deleted a rule',
    ])
    await user.click(within(listbox).getByRole('option', { name: 'Deleted a rule' }))

    await waitFor(() => expect(router.state.location.search).toEqual({ entity_type: 'rule', action: 'rule.deleted' }))
    await waitFor(() => expect(queries.at(-1)?.getAll('action')).toEqual(['rule.deleted']))
  })

  test('a time range sends since, counted back from when it was picked, in one request', async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]))
    const queries = recordAuditQueries()
    const { findByRole, getByRole, user, router } = openAs(petraIn('member'), PATH)
    await findByRole('table', { name: 'Audit log' })
    const before = queries.length

    await user.click(getByRole('button', { name: 'Last 7 days' }))

    await waitFor(() => expect(router.state.location.search).toEqual({ range: '7d' }))
    await waitFor(() => expect(queries.length).toBe(before + 1))
    const since = Date.parse(queries.at(-1)?.get('since') ?? '')
    expect(Date.now() - since).toBeGreaterThanOrEqual(7 * 24 * 60 * 60_000)
    expect(Date.now() - since).toBeLessThan(7 * 24 * 60 * 60_000 + 60_000)

    await user.click(getByRole('button', { name: 'All time' }))

    await waitFor(() => expect(router.state.location.search).toEqual({}))
  })

  test('Who offers the system and searches people by name', async () => {
    server.use(
      respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]),
      respond(listUsers, 'get', getListUsersUrl(), 200, [ola]),
    )
    const queries = recordAuditQueries()
    const { findByRole, getByRole, user, router } = openAs(petraIn('member'), PATH)
    await findByRole('table', { name: 'Audit log' })

    await user.click(getByRole('combobox', { name: 'Who' }))
    await user.click(await findByRole('option', { name: 'System' }))

    await waitFor(() => expect(router.state.location.search).toEqual({ system: true }))
    await waitFor(() => expect(queries.at(-1)?.get('system')).toBe('true'))

    await user.clear(getByRole('combobox', { name: 'Who' }))
    await user.type(getByRole('combobox', { name: 'Who' }), 'ola')
    await user.click(await findByRole('option', { name: /Ola Berg/ }))

    await waitFor(() => expect(router.state.location.search).toEqual({ actor_user_id: namedUser }))
    await waitFor(() => expect(queries.at(-1)?.get('actor_user_id')).toBe(namedUser))
    expect(queries.at(-1)?.has('system')).toBe(false)
  })

  test("an entry's id link filters to that entity; its chip removes the filter", async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]))
    const queries = recordAuditQueries()
    const { findByRole, getByRole, user, router } = openAs(petraIn('member'), PATH)

    await user.click(await findByRole('link', { name: `Show the history of alert ${alertId}` }))

    await waitFor(() => expect(router.state.location.search).toEqual({ entity_type: 'alert', entity_id: alertId }))
    await waitFor(() => expect(queries.at(-1)?.get('entity_id')).toBe(alertId))

    await user.click(getByRole('button', { name: `Stop filtering by alert ${alertId}` }))

    await waitFor(() => expect(router.state.location.search).toEqual({ entity_type: 'alert' }))
  })

  test('Filter by ID applies a full id and keeps one that is not with an error', async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]))
    const { findByRole, findByLabelText, findByText, getByRole, user, router } = openAs(petraIn('member'), PATH)
    await findByRole('table', { name: 'Audit log' })

    await user.click(getByRole('button', { name: 'Filter by ID' }))
    const field = await findByLabelText('Entity ID')
    await user.type(field, '0193c000')
    await user.click(getByRole('button', { name: 'Apply filter' }))

    expect(await findByText('Enter the full entity ID, 36 characters with dashes.')).toBeInTheDocument()
    expect(field).toHaveAttribute('aria-invalid', 'true')
    expect(router.state.location.search).toEqual({})

    await user.clear(field)
    await user.type(field, alertId)
    await user.click(getByRole('button', { name: 'Apply filter' }))

    await waitFor(() => expect(router.state.location.search).toEqual({ entity_id: alertId }))
  })

  test('a hand-edited id in the address that does not parse is dropped', async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, []))
    const queries = recordAuditQueries()

    const { findByText } = openAs(petraIn('member'), `${PATH}?entity_id=nope`)

    expect(await findByText('Nothing recorded yet')).toBeInTheDocument()
    expect(queries.at(-1)?.has('entity_id')).toBe(false)
  })

  test('Show more loads the next 100 entries while the last page was full', async () => {
    const queries = recordAuditQueries()
    const firstPage = Array.from({ length: 100 }, () => entry())
    server.use(
      http.get(getListAuditEntriesUrl(), ({ request }) => {
        const offset = new URL(request.url).searchParams.get('offset')
        return HttpResponse.json(offset === '0' ? firstPage : [entry({ action: 'team.updated' })])
      }),
    )
    const { findByRole, findByText, queryByRole, user } = openAs(petraIn('member'), PATH)

    await user.click(await findByRole('button', { name: 'Show more' }))

    expect(await findByText('Renamed or described the team')).toBeInTheDocument()
    expect(queries.map((query) => query.get('offset'))).toEqual(['0', '100'])
    expect(queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument()
  })

  test('shows skeleton rows while the first page loads', async () => {
    server.use(
      http.get(getListAuditEntriesUrl(), async () => {
        await delay('infinite')
        return HttpResponse.json([])
      }),
    )
    const { findByRole, getAllByTestId } = openAs(petraIn('member'), PATH)

    expect(await findByRole('table', { name: 'Audit log' })).toHaveAttribute('aria-busy', 'true')
    expect(getAllByTestId('skeleton-row').length).toBeGreaterThan(0)
  })

  test('an empty log says nothing was recorded; an empty filtered log offers Clear filters', async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, []))
    const { findByText, findByRole, user, router } = openAs(petraIn('member'), `${PATH}?entity_type=rule`)

    expect(await findByText('No entries match these filters')).toBeInTheDocument()
    const main = await findByRole('main')
    await user.click(nth(within(main).getAllByRole('button', { name: 'Clear filters' }), -1))

    await waitFor(() => expect(router.state.location.search).toEqual({}))
    expect(await findByText('Nothing recorded yet')).toBeInTheDocument()
  })

  test('a 422 says the filters are not valid, with Try again', async () => {
    server.use(
      respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 422, {
        detail: [{ loc: ['query', 'entity_id'], msg: 'Input should be a valid UUID', type: 'uuid_parsing' }],
      }),
    )
    const { findByRole } = openAs(petraIn('member'), PATH)

    const failure = await findByRole('alert')
    expect(failure).toHaveTextContent("Couldn't load the audit log")
    expect(failure).toHaveTextContent("The filters aren't valid. Clear them and try again.")
    expect(await findByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  test('a 403, which the contract does not document, gets the shared fallback message', async () => {
    server.use(http.get(getListAuditEntriesUrl(), () => HttpResponse.json({ detail: 'Forbidden' }, { status: 403 })))
    const { findByRole } = openAs(petraIn('member'), PATH)

    expect(await findByRole('alert')).toHaveTextContent(
      'Something went wrong on the server (HTTP 403). Try again in a moment.',
    )
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(
      http.get(getListAuditEntriesUrl(), () => HttpResponse.json({ detail: 'Not implemented' }, { status: 501 })),
    )
    const { findByRole } = openAs(petraIn('member'), PATH)

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('GET /audit on the admin audit log', () => {
  test('an admin sees every team: the request carries no team', async () => {
    server.use(
      respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [
        entry({ action: 'team.created', entity_type: 'team', entity_id: settlements.id, team_id: settlements.id }),
        entry({ action: 'user.created', entity_type: 'user', entity_id: otherUser, team_id: null }),
      ]),
    )
    const queries = recordAuditQueries()

    const { findByRole } = openAs(petra('admin', []), '/admin/audit')

    const table = await findByRole('table', { name: 'Audit log' })
    expect(queries.at(-1)?.has('team_id')).toBe(false)
    expect(await within(table).findByRole('link', { name: 'Team' })).toHaveAttribute('href', '/teams/settlements/alerts')
    expect(within(table).getByRole('link', { name: 'User' })).toHaveAttribute('href', '/admin/users')
    expect(
      within(table).getByRole('link', { name: `Show the history of user ${otherUser}` }),
    ).toHaveAttribute('href', `/admin/audit?entity_type=user&entity_id=${otherUser}`)
  })

  test('the team filter picks one team or the entries without a team', async () => {
    const payments = { ...team('payments', 'Payments'), id: '0193b000-0000-7000-8000-0000000000e1' }
    server.use(
      respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]),
      respond(listTeams, 'get', getListTeamsUrl(), 200, [payments]),
    )
    const queries = recordAuditQueries()
    const { findByRole, getByLabelText, user, router } = openAs(petra('admin', []), '/admin/audit')
    await findByRole('table', { name: 'Audit log' })

    await user.click(getByLabelText('Team'))
    const listbox = await findByRole('listbox')
    expect(within(listbox).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'All teams',
      'No team',
      'Payments',
    ])
    await user.click(within(listbox).getByRole('option', { name: 'No team' }))

    await waitFor(() => expect(router.state.location.search).toEqual({ without_team: true }))
    await waitFor(() => expect(queries.at(-1)?.get('without_team')).toBe('true'))

    await user.click(getByLabelText('Team'))
    await user.click(await findByRole('option', { name: 'Payments' }))

    await waitFor(() => expect(router.state.location.search).toEqual({ team_id: payments.id }))
    await waitFor(() => expect(queries.at(-1)?.get('team_id')).toBe(payments.id))
    expect(queries.at(-1)?.has('without_team')).toBe(false)
  })

  test('a non-admin gets the 404 page', async () => {
    const { findByRole } = openAs(petraIn('lead'), '/admin/audit')

    expect(await findByRole('alert')).toHaveTextContent('Page not found')
  })
})
