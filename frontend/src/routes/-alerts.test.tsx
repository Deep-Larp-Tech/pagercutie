import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import { getListAlertsUrl } from '@/api/generated/alerts/alerts'
import { getGetMeUrl, getMe } from '@/api/generated/auth/auth'
import type { AlertRead, MeRead } from '@/api/generated/model'
import { getGetTeamOnCallUrl, getTeamOnCall } from '@/api/generated/teams/teams'
import { alert } from '@/test/alerts'
import { respond } from '@/test/http'
import { membership, petra, team } from '@/test/people'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const settlements = team('settlements', 'Settlements')
const payments = team('payments', 'Payments')
const me: MeRead = petra('user', [membership(settlements, 'member'), membership(payments, 'viewer')])

/** Answers `GET /alerts` with `alerts` and records each request's query parameters. */
function recordAlerts(alerts: AlertRead[] = []) {
  const queries: URLSearchParams[] = []
  server.use(
    http.get(getListAlertsUrl(), ({ request }) => {
      queries.push(new URL(request.url).searchParams)
      return HttpResponse.json(alerts)
    }),
  )
  return queries
}

describe('/teams/$team/alerts', () => {
  test('loads open and acknowledged alerts of the team by default', async () => {
    server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
    const queries = recordAlerts()

    const { findByText } = renderApp('/teams/settlements/alerts')

    expect(await findByText('No open alerts')).toBeInTheDocument()
    expect(queries.at(-1)?.get('team_id')).toBe(settlements.id)
    expect(queries.at(-1)?.getAll('status')).toEqual(['open', 'acknowledged'])
    expect(queries.at(-1)?.getAll('severity')).toEqual([])
  })

  test('the filters go into the address and the request', async () => {
    server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
    const queries = recordAlerts()
    const { findByRole, user, router } = renderApp('/teams/settlements/alerts')
    const severity = await findByRole('group', { name: 'Severity' })

    await user.click(within(severity).getByRole('button', { name: 'Critical' }))
    await user.click(within(await findByRole('group', { name: 'Status' })).getByRole('button', { name: 'Resolved' }))

    await waitFor(() => expect(queries.at(-1)?.getAll('status')).toEqual(['open', 'acknowledged', 'resolved']))
    expect(queries.at(-1)?.getAll('severity')).toEqual(['critical'])
    expect(router.state.location.search).toEqual({
      status: ['open', 'acknowledged', 'resolved'],
      severity: ['critical'],
    })
  })

  test('an unreadable filter in the address falls back to the default feed', async () => {
    server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
    const queries = recordAlerts()

    const { findByText } = renderApp('/teams/settlements/alerts?status=%22sideways%22')

    expect(await findByText('No open alerts')).toBeInTheDocument()
    expect(queries.at(-1)?.getAll('status')).toEqual(['open', 'acknowledged'])
  })

  test('the empty state links to the team rules, or clears active filters', async () => {
    server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
    recordAlerts()

    const { findByRole, user } = renderApp('/teams/settlements/alerts?severity=%5B%22debug%22%5D')

    await user.click(await findByRole('link', { name: 'Clear filters' }))
    expect(await findByRole('link', { name: 'Open rules' })).toHaveAttribute('href', '/teams/settlements/rules')
  })
})

describe('/ Overview', () => {
  test('shows who is on call per team, then open and acknowledged alerts across teams', async () => {
    server.use(
      respond(getMe, 'get', getGetMeUrl(), 200, me),
      respond(getTeamOnCall, 'get', getGetTeamOnCallUrl(settlements.id), 200, {
        team_id: settlements.id,
        user: me.user,
        until: '2026-11-23T08:00:00Z',
      }),
      respond(getTeamOnCall, 'get', getGetTeamOnCallUrl(payments.id), 200, {
        team_id: payments.id,
        user: null,
        until: null,
      }),
    )
    const item = alert(settlements.id)
    const personal = alert(null, { title: 'My card was charged twice', severity: 'warn', colour: 'yellow' })
    const queries = recordAlerts([item, personal])

    const { findByRole, findByText } = renderApp('/')

    const settlementsCard = await findByRole('region', { name: 'On call for Settlements' })
    expect(await within(settlementsCard).findByText("You're on call until Mon 09:00")).toBeInTheDocument()
    expect(await findByText('No rotation set')).toBeInTheDocument()

    const card = await findByRole('article', { name: item.title })
    expect(within(card).getByText('Settlements')).toBeInTheDocument()
    expect(within(await findByRole('article', { name: personal.title })).getByText('Personal rule')).toBeInTheDocument()
    expect(queries.at(-1)?.has('team_id')).toBe(false)
    expect(queries.at(-1)?.getAll('status')).toEqual(['open', 'acknowledged'])
  })
})
