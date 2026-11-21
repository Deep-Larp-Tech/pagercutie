import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import type { RuleRead } from '@/api/generated/model'
import { getListRulesUrl, getUpdateRuleUrl, listRules, updateRule } from '@/api/generated/rules/rules'
import { getListUsersUrl, listUsers } from '@/api/generated/users/users'
import { respond } from '@/test/http'
import { membership, petra } from '@/test/people'
import { settlementsRule } from '@/test/rules'
import { server } from '@/test/server'
import { openAs, petraIn, recordRequests, settlements, user } from '@/test/teams'

const PATH = '/teams/settlements/rules'
const rulesUrl = getListRulesUrl()
const rule = settlementsRule()

function withRules(rules: RuleRead[]) {
  server.use(respond(listRules, 'get', rulesUrl, 200, rules))
}

describe('GET /rules (team)', () => {
  test('lists name, on switch, severity in the rule colour, recipients; filters by the team', async () => {
    withRules([rule, settlementsRule({ id: 'rule-2', name: 'Payout late', enabled: false, presentation: { ...rule.presentation, severity: 'warn', colour: 'green' } })])

    const { findByRole, getByRole } = openAs(petraIn('member'), PATH)
    await findByRole('link', { name: 'Payout late' })
    const table = getByRole('table', { name: 'Rules' })

    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('Order settlement failed in prod')
    expect(rows[0]).toHaveTextContent('Critical')
    expect(rows[0]).toHaveTextContent('On call in Settlements')
    expect(within(rows[1] ?? table).getByText('Warning').closest('.alert-green')).not.toBeNull()
    expect(getByRole('switch', { name: 'Rule Order settlement failed in prod is on' })).toBeChecked()
    expect(getByRole('switch', { name: 'Rule Payout late is on' })).not.toBeChecked()
    expect(getByRole('link', { name: 'Order settlement failed in prod' })).toHaveAttribute(
      'href',
      '/teams/settlements/rules/rule-settlement-failed',
    )
    expect(getByRole('link', { name: 'New rule' })).toHaveAttribute('href', '/teams/settlements/rules/new')
  })

  test('sends team_id and limit', async () => {
    let query: URLSearchParams | null = null
    server.use(
      http.get(rulesUrl, ({ request }) => {
        query = new URL(request.url).searchParams
        return HttpResponse.json([])
      }),
    )

    const { findByText } = openAs(petraIn('member'), PATH)

    expect(await findByText('No rules yet')).toBeInTheDocument()
    expect(query).not.toBeNull()
    expect(Object.fromEntries(query ?? [])).toEqual({ team_id: settlements.id, limit: '100', offset: '0' })
  })

  test('user recipients are named from GET /users', async () => {
    const bob = user('bob', 'Bob Novak')
    withRules([settlementsRule({ routing: { recipients: [{ type: 'user', user_id: bob.id }, { type: 'team', team_id: settlements.id }] } })])
    server.use(respond(listUsers, 'get', getListUsersUrl(), 200, [bob]))

    const { findByText } = openAs(petraIn('member'), PATH)

    expect(await findByText('Bob Novak, Everyone in Settlements')).toBeInTheDocument()
  })

  test('the empty state offers New rule to members', async () => {
    withRules([])

    const { findByText, getAllByRole } = openAs(petraIn('lead'), PATH)

    expect(await findByText('Without rules no event becomes an alert. Add the first one with New rule.')).toBeInTheDocument()
    expect(getAllByRole('link', { name: 'New rule' })).toHaveLength(2)
  })

  test('a viewer reads the list without switches or New rule', async () => {
    withRules([rule])

    const { findByRole, queryByRole, getByText, getByRole } = openAs(petraIn('viewer'), PATH)
    await findByRole('link', { name: rule.name })
    const table = getByRole('table')

    expect(within(table).getAllByRole('row')[1]).toHaveTextContent('On')
    expect(queryByRole('switch')).not.toBeInTheDocument()
    expect(queryByRole('link', { name: 'New rule' })).not.toBeInTheDocument()
    expect(getByText('Only members and leads of this team can change its rules.')).toBeInTheDocument()
  })

  test('422 says the request was not valid', async () => {
    server.use(respond(listRules, 'get', rulesUrl, 422, { detail: [{ loc: ['query', 'team_id'], msg: 'bad', type: 'uuid' }] }))

    const { findByRole } = openAs(petraIn('member'), PATH)

    expect(await findByRole('alert')).toHaveTextContent('The list request was not valid. Reload the page and try again.')
  })

  test('the 501 stub shows the shared fallback with Try again', async () => {
    server.use(http.get(rulesUrl, () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole, getByRole } = openAs(petraIn('member'), PATH)

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
    expect(getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('GET /rules (personal)', () => {
  const me = petra('user', [membership(settlements, 'member')])

  test('lists my rules filtered by user_id; recipients read You', async () => {
    let query: URLSearchParams | null = null
    server.use(
      http.get(rulesUrl, ({ request }) => {
        query = new URL(request.url).searchParams
        return HttpResponse.json([
          settlementsRule({
            id: 'rule-anna',
            name: 'Payments API critical',
            owner: { type: 'user', user_id: me.user.id },
            routing: { recipients: [{ type: 'user', user_id: me.user.id }], channels: null },
          }),
        ])
      }),
    )

    const { findByRole, getByRole } = openAs(me, '/me/rules')
    await findByRole('link', { name: 'Payments API critical' })
    const table = getByRole('table', { name: 'My rules' })

    expect(within(table).getAllByRole('row')[1]).toHaveTextContent('You')
    expect(Object.fromEntries(query ?? [])).toMatchObject({ user_id: me.user.id })
    expect(getByRole('link', { name: 'Payments API critical' })).toHaveAttribute('href', '/me/rules/rule-anna')
    expect(getByRole('link', { name: 'New rule' })).toHaveAttribute('href', '/me/rules/new')
  })
})

describe('PATCH /rules/{id} (on switch)', () => {
  const url = getUpdateRuleUrl(rule.id)

  async function toggle() {
    withRules([rule])
    const rendered = openAs(petraIn('member'), PATH)
    await rendered.user.click(await rendered.findByRole('switch', { name: 'Rule Order settlement failed in prod is on' }))
    return rendered
  }

  test('200 sends only enabled and reloads the list', async () => {
    server.use(respond(updateRule, 'patch', url, 200, { ...rule, enabled: false }))
    const patches = recordRequests('patch', url)
    const lists = recordRequests('get', rulesUrl)

    await toggle()

    await waitFor(() => expect(patches.map(({ body }) => body)).toEqual([{ enabled: false }]))
    await waitFor(() => expect(lists.length).toBeGreaterThan(0))
  })

  test.each([
    [403, 'Couldn\'t switch off Order settlement failed in prod. Only members and leads of this team can change its rules.'],
    [404, "Couldn't switch off Order settlement failed in prod. This rule doesn't exist anymore. It may have been deleted."],
  ] as const)('%i shows why', async (status, message) => {
    server.use(respond(updateRule, 'patch', url, status, { detail: 'x' }))

    const { findByRole } = await toggle()

    expect(await findByRole('alert')).toHaveTextContent(message)
  })

  test('422 shows the first message', async () => {
    server.use(respond(updateRule, 'patch', url, 422, { detail: [{ loc: ['body', 'enabled'], msg: 'Input should be a valid boolean', type: 'bool' }] }))

    const { findByRole } = await toggle()

    expect(await findByRole('alert')).toHaveTextContent('Input should be a valid boolean')
  })

  test('an undocumented 409 shows the shared fallback', async () => {
    server.use(http.patch(url, () => HttpResponse.json({ detail: 'x' }, { status: 409 })))

    const { findByRole } = await toggle()

    expect(await findByRole('alert')).toHaveTextContent('Something went wrong on the server (HTTP 409).')
  })
})
