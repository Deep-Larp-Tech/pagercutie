import { http, HttpResponse, delay } from 'msw'
import { describe, expect, test } from 'vitest'
import { getGetTeamOnCallUrl, getTeamOnCall } from '@/api/generated/teams/teams'
import type { UserRead } from '@/api/generated/model'
import { respond } from '@/test/http'
import { membership, petra, team } from '@/test/people'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { OnCallCard } from './on-call-card'

const settlements = team('settlements', 'Settlements')
const me = petra('user', [membership(settlements, 'member')])
const anna: UserRead = {
  id: '0193a000-0000-7000-8000-000000000001',
  email: 'anna@example.com',
  display_name: 'Anna Novak',
  phone: null,
  timezone: 'Europe/Prague',
  role: 'user',
  created_at: '2026-01-01T00:00:00Z',
}

function renderCard() {
  return renderWithProviders(<OnCallCard team={settlements} />, { me })
}

function onCall(user: UserRead | null, until: string | null) {
  return respond(getTeamOnCall, 'get', getGetTeamOnCallUrl(settlements.id), 200, {
    team_id: settlements.id,
    user,
    until,
  })
}

describe('GET /teams/{id}/on-call', () => {
  test('says when your own shift ends, in your time zone', async () => {
    server.use(onCall(me.user, '2026-11-23T08:00:00Z'))

    const { findByText, getByRole } = renderCard()

    expect(await findByText("You're on call until Mon 09:00")).toBeInTheDocument()
    expect(getByRole('region', { name: 'On call for Settlements' })).toBeInTheDocument()
  })

  test('names someone else who is on call', async () => {
    server.use(onCall(anna, '2026-11-23T08:00:00Z'))

    const { findByText } = renderCard()

    expect(await findByText('Anna Novak is on call')).toBeInTheDocument()
  })

  test('says so when the team has no rotation', async () => {
    server.use(onCall(null, null))

    const { findByText } = renderCard()

    expect(await findByText('No rotation set')).toBeInTheDocument()
  })

  test('shows a skeleton while loading', async () => {
    server.use(http.get(getGetTeamOnCallUrl(settlements.id), async () => delay('infinite')))

    const { findByRole, container } = renderCard()

    expect(await findByRole('region', { name: 'On call for Settlements' })).toBeInTheDocument()
    expect(container.querySelector('[data-slot="skeleton"]')).toBeInTheDocument()
  })

  test('404 says the rotation was not found', async () => {
    server.use(respond(getTeamOnCall, 'get', getGetTeamOnCallUrl(settlements.id), 404, { detail: 'No team' }))

    const { findByRole } = renderCard()

    expect(await findByRole('alert')).toHaveTextContent("Couldn't find this team's rotation.")
  })

  test('422 says who is on call could not be loaded', async () => {
    server.use(respond(getTeamOnCall, 'get', getGetTeamOnCallUrl(settlements.id), 422, { detail: [] }))

    const { findByRole } = renderCard()

    expect(await findByRole('alert')).toHaveTextContent("Couldn't load who is on call.")
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(
      http.get(getGetTeamOnCallUrl(settlements.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )

    const { findByRole } = renderCard()

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})
