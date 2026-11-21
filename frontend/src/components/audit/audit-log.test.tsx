import { delay, http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, onTestFinished, test } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import { getListAuditEntriesUrl, listAuditEntries } from '@/api/generated/audit/audit'
import type { AuditEntryRead } from '@/api/generated/model'
import { getListTeamsUrl, listTeams } from '@/api/generated/teams/teams'
import { respond } from '@/test/http'
import { petra } from '@/test/people'
import { server } from '@/test/server'
import { openAs, petraIn, settlements } from '@/test/teams'
import { nth } from '@/test/elements'

const PATH = '/teams/settlements/audit'
const alertId = '0193c000-0000-7000-8000-00000000a1e7'
const otherUser = '0193a000-0000-7000-8000-0000000000b0'

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
        entry({ actor_user_id: null, action: 'step.approval_requested', data: { step: 'reserve-funds' } }),
        entry({ actor_user_id: otherUser, action: 'rule.updated', entity_type: 'rule' }),
      ]),
    )
    const { findByRole, getByRole, user } = openAs(lead, PATH)

    const table = await findByRole('table', { name: 'Audit log' })
    await within(table).findByText('Rule updated')
    const rows = within(table).getAllByRole('row')
    expect(rows.slice(1).map((row) => within(row).getAllByRole('cell')[1]?.textContent)).toEqual([
      'You',
      'System',
      'User 0193a000',
    ])
    expect(within(table).getByText('Acknowledged the alert')).toBeInTheDocument()
    expect(within(table).getByText('Step approval requested')).toBeInTheDocument()
    expect(within(table).getByRole('link', { name: 'Rule' })).toHaveAttribute('href', '/teams/settlements/rules')
    expect(within(table).getAllByRole('link', { name: 'Alert' })[0]).toHaveAttribute(
      'href',
      '/teams/settlements/alerts',
    )

    await user.click(getByRole('button', { name: 'Show details of Step approval requested' }))

    expect(within(table).getByText(/"step": "reserve-funds"/)).toBeInTheDocument()
    expect(getByRole('button', { name: 'Hide details of Step approval requested' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  test('filters in the address go into the request, with the team and the page size', async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]))
    const queries = recordAuditQueries()

    const { findByRole, getByLabelText } = openAs(petraIn('viewer'), `${PATH}?entity_type=alert&entity_id=${alertId}`)

    await findByRole('table', { name: 'Audit log' })
    expect(Object.fromEntries(queries.at(-1) ?? [])).toEqual({
      team_id: settlements.id,
      entity_type: 'alert',
      entity_id: alertId,
      limit: '100',
      offset: '0',
    })
    expect(getByLabelText('Entity type')).toHaveValue('alert')
    expect(getByLabelText('Entity ID')).toHaveValue(alertId)
  })

  test('Apply filters writes them to the address; an entity id link filters to that entity', async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]))
    const queries = recordAuditQueries()
    const { findByRole, getByLabelText, getByRole, user, router } = openAs(petraIn('member'), PATH)
    await findByRole('table', { name: 'Audit log' })

    await user.type(getByLabelText('Entity type'), 'rule')
    await user.click(getByRole('button', { name: 'Apply filters' }))

    await waitFor(() => expect(router.state.location.search).toEqual({ entity_type: 'rule' }))
    await waitFor(() => expect(queries.at(-1)?.get('entity_type')).toBe('rule'))

    await user.click(await findByRole('link', { name: `Show the history of alert ${alertId}` }))

    await waitFor(() => expect(router.state.location.search).toEqual({ entity_type: 'alert', entity_id: alertId }))
    await waitFor(() => expect(queries.at(-1)?.get('entity_id')).toBe(alertId))
  })

  test('an entity id that is not a full id stays in the form with an error', async () => {
    server.use(respond(listAuditEntries, 'get', getListAuditEntriesUrl(), 200, [entry()]))
    const { findByRole, getByLabelText, getByRole, findByText, user, router } = openAs(petraIn('member'), PATH)
    await findByRole('table', { name: 'Audit log' })

    await user.type(getByLabelText('Entity ID'), '0193c000')
    await user.click(getByRole('button', { name: 'Apply filters' }))

    expect(await findByText('Enter the full entity ID, 36 characters with dashes.')).toBeInTheDocument()
    expect(getByLabelText('Entity ID')).toHaveAttribute('aria-invalid', 'true')
    expect(router.state.location.search).toEqual({})
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

    expect(await findByText('Team updated')).toBeInTheDocument()
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
    expect(failure).toHaveTextContent("The filters aren't valid. Check the entity ID and try again.")
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

  test('a non-admin gets the 404 page', async () => {
    const { findByRole } = openAs(petraIn('lead'), '/admin/audit')

    expect(await findByRole('alert')).toHaveTextContent('Page not found')
  })
})
