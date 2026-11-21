import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { within } from '@testing-library/react'
import { getGetMeUrl, getMe } from '@/api/generated/auth/auth'
import type { MeRead } from '@/api/generated/model'
import { getListTeamsUrl, listTeams } from '@/api/generated/teams/teams'
import { respond } from '@/test/http'
import { membership, petra, team } from '@/test/people'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const settlements = team('settlements', 'Settlements')
const payments = team('payments', 'Payments')
const billing = team('billing', 'Billing')

async function openSwitcher(me: MeRead, route = '/teams/settlements/alerts') {
  server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
  const rendered = renderApp(route)
  await rendered.user.click(await rendered.findByRole('button', { name: 'Team: Settlements. Switch team' }))
  const menu = await rendered.findByRole('menu')
  return { ...rendered, menu }
}

function teamNames(menu: HTMLElement): string[] {
  return within(menu)
    .getAllByRole('menuitem')
    .map((item) => item.textContent ?? '')
}

describe('GET /teams in the team switcher', () => {
  test('an admin sees their teams, then every other team from the response', async () => {
    const me = petra('admin', [membership(settlements, 'lead')])
    server.use(respond(listTeams, 'get', getListTeamsUrl(), 200, [payments, settlements, billing]))

    const { menu } = await openSwitcher(me)

    expect(await within(menu).findByText('Other teams')).toBeInTheDocument()
    expect(teamNames(menu)).toEqual(['SettlementsLead', 'Billing', 'Payments'])
  })

  test('a non-admin sees their memberships and sends no request', async () => {
    // No GET /teams handler: MSW fails the test if the switcher asks for the list.
    const me = petra('user', [membership(settlements, 'viewer'), membership(payments, 'member')])

    const { menu } = await openSwitcher(me)

    expect(teamNames(menu)).toEqual(['SettlementsViewer', 'PaymentsMember'])
    expect(within(menu).queryByText('Other teams')).not.toBeInTheDocument()
  })

  test('the 501 stub falls back to memberships without a message', async () => {
    const me = petra('admin', [membership(settlements, 'member')])
    server.use(http.get(getListTeamsUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { menu } = await openSwitcher(me)

    expect(teamNames(menu)).toEqual(['SettlementsMember'])
    expect(within(menu).queryByRole('alert')).not.toBeInTheDocument()
  })

  test('422 falls back to memberships and says so', async () => {
    const me = petra('admin', [membership(settlements, 'member')])
    server.use(respond(listTeams, 'get', getListTeamsUrl(), 422, { detail: [] }))

    const { menu } = await openSwitcher(me)

    expect(await within(menu).findByRole('alert')).toHaveTextContent(
      "Couldn't load every team. Showing your teams only.",
    )
    expect(teamNames(menu)).toEqual(['SettlementsMember'])
  })

  test('picking a team opens the same page in that team', async () => {
    const me = petra('user', [membership(settlements, 'member'), membership(payments, 'member')])

    const { menu, user, router, findByRole } = await openSwitcher(me, '/teams/settlements/rules')
    await user.click(within(menu).getByRole('menuitem', { name: /Payments/ }))

    expect(await findByRole('button', { name: 'Team: Payments. Switch team' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/teams/payments/rules')
  })
})
