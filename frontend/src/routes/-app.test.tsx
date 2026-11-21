import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, test } from 'vitest'
import { waitFor } from '@testing-library/react'
import { getGetMeUrl, getMe } from '@/api/generated/auth/auth'
import { getGetMeResponseMock } from '@/api/generated/auth/auth.faker'
import { getListTeamsQueryOptions, getListTeamsUrl, listTeams } from '@/api/generated/teams/teams'
import { respond } from '@/test/http'
import { renderApp, renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { useMe } from '@/lib/session'
import { quietFeedEndpoints } from '@/test/alerts'

// The Overview and the team alerts page load alerts and on-call answers; these tests are about something else.
beforeEach(() => server.use(...quietFeedEndpoints()))

const me = getGetMeResponseMock({
  user: {
    id: '0193a000-0000-7000-8000-000000000002',
    email: 'petra@example.com',
    display_name: 'Petra Dvorak',
    phone: null,
    timezone: 'Europe/Prague',
    role: 'user',
    created_at: '2026-01-01T00:00:00Z',
  },
  memberships: [],
})

describe('GET /me in the authenticated layout', () => {
  test('200 renders the page in the shell with the user', async () => {
    server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))

    const { findByRole, getByRole } = renderApp('/')

    expect(await findByRole('button', { name: 'Petra Dvorak, account menu' })).toBeInTheDocument()
    expect(getByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument()
  })

  test('401 sends the user to /login with the page as redirect', async () => {
    server.use(respond(getMe, 'get', getGetMeUrl(), 401, { detail: 'Not signed in.' }))

    const { findByLabelText, router } = renderApp('/?from=chat')

    expect(await findByLabelText('Work email')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.search).toEqual({ redirect: '/?from=chat' })
  })

  test('an undocumented status shows the error page', async () => {
    server.use(http.get(getGetMeUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 502 })))

    const { findByRole } = renderApp('/')

    expect(await findByRole('alert')).toHaveTextContent(
      "Couldn't load your account" +
        'Something went wrong on the server (HTTP 502). Try again in a moment.',
    )
  })

  test('a 401 from any later query sends the user to /login', async () => {
    server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
    const { findByRole, findByLabelText, queryClient, router } = renderApp('/')
    expect(await findByRole('button', { name: 'Petra Dvorak, account menu' })).toBeInTheDocument()

    server.use(
      respond(getMe, 'get', getGetMeUrl(), 401, { detail: 'Session expired.' }),
      respond(listTeams, 'get', getListTeamsUrl(), 401, { detail: 'Session expired.' }),
    )
    await queryClient.fetchQuery(getListTeamsQueryOptions())

    expect(await findByLabelText('Work email')).toBeInTheDocument()
    await waitFor(() => expect(router.state.location.search).toEqual({ redirect: '/' }))
    expect(router.state.location.pathname).toBe('/login')
  })
})

function Greeting() {
  return <p>Hello {useMe().user.display_name}</p>
}

test('renderWithProviders injects the signed-in user', async () => {
  const { findByText } = renderWithProviders(<Greeting />, { route: '/me/profile', me })

  expect(await findByText('Hello Petra Dvorak')).toBeInTheDocument()
})
