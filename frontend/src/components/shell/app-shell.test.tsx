import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, test } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { render, waitFor, within } from '@testing-library/react'
import { getGetMeUrl, getMe } from '@/api/generated/auth/auth'
import type { MeRead, TeamRole } from '@/api/generated/model'
import { getListTeamsUrl, listTeams } from '@/api/generated/teams/teams'
import type { RouterContext } from '@/routes/__root'
import { respond } from '@/test/http'
import { membership, petra, team } from '@/test/people'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'
import { AppShell } from './app-shell'
import { quietFeedEndpoints } from '@/test/alerts'

// The Overview and the team alerts page load alerts and on-call answers; these tests are about something else.
beforeEach(() => server.use(...quietFeedEndpoints()))

const settlements = team('settlements', 'Settlements')
const payments = team('payments', 'Payments')

const teamLinks = ['Alerts', 'Rules', 'Runbooks', 'Sources', 'Schemas', 'Settings', 'Audit log']

function signedInAs(me: MeRead, route: string) {
  server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
  return renderApp(route)
}

function linkNames(nav: HTMLElement): string[] {
  return within(nav)
    .getAllByRole('link')
    .map((link) => link.textContent ?? '')
}

afterEach(() => {
  localStorage.clear()
  delete document.documentElement.dataset.theme
})

describe('sidebar navigation per role', () => {
  test('an admin sees the Admin section', async () => {
    server.use(respond(listTeams, 'get', getListTeamsUrl(), 200, [settlements]))
    const { findByRole } = signedInAs(petra('admin', []), '/')

    const nav = await findByRole('navigation', { name: 'Main' })

    expect(await within(nav).findByRole('link', { name: 'Alerts' })).toBeInTheDocument()
    expect(within(nav).getByRole('heading', { name: 'Admin' })).toBeInTheDocument()
    expect(linkNames(nav)).toEqual(['Overview', ...teamLinks, 'My rules', 'Notifications', 'Users', 'Teams', 'Audit log'])
  })

  test.each<TeamRole>(['viewer', 'member', 'lead'])(
    'a %s sees every team page and no Admin section',
    async (role) => {
      const { findByRole } = signedInAs(petra('user', [membership(settlements, role)]), '/')

      const nav = await findByRole('navigation', { name: 'Main' })

      // Every team role may read every team page (DOMAIN.md §4); edit controls are hidden inside the pages.
      expect(linkNames(nav)).toEqual(['Overview', ...teamLinks, 'My rules', 'Notifications'])
      expect(within(nav).queryByRole('heading', { name: 'Admin' })).not.toBeInTheDocument()
    },
  )

  test('a user with no team sees a line instead of the team pages', async () => {
    const { findByRole, getByText } = signedInAs(petra('user', []), '/')

    const nav = await findByRole('navigation', { name: 'Main' })

    expect(getByText("You're not in a team yet. Ask an admin to add you.")).toBeInTheDocument()
    expect(linkNames(nav)).toEqual(['Overview', 'My rules', 'Notifications'])
  })

  test('an admin with no team while GET /teams is a stub sees a calm line', async () => {
    server.use(http.get(getListTeamsUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const { findByText, queryByRole } = signedInAs(petra('admin', []), '/')

    expect(await findByText("You're not in a team yet. Add teams under Admin.")).toBeInTheDocument()
    expect(queryByRole('alert')).not.toBeInTheDocument()
  })

  test('the active link is marked as the current page', async () => {
    const { findByRole } = signedInAs(petra('user', [membership(settlements, 'member')]), '/teams/settlements/rules')

    const nav = await findByRole('navigation', { name: 'Main' })

    await waitFor(() => expect(within(nav).getByRole('link', { name: 'Rules' })).toHaveAttribute('aria-current', 'page'))
    expect(within(nav).getByRole('link', { name: 'Overview' })).not.toHaveAttribute('aria-current')
  })

  test('the sliding highlight follows the active link', async () => {
    const { findByRole, user } = signedInAs(petra('user', [membership(settlements, 'member')]), '/teams/settlements/rules')
    const nav = await findByRole('navigation', { name: 'Main' })
    const highlightIn = (name: string) => within(within(nav).getByRole('link', { name })).queryByTestId('nav-highlight')

    await waitFor(() => expect(highlightIn('Rules')).not.toBeNull())

    await user.click(within(nav).getByRole('link', { name: 'Runbooks' }))

    await waitFor(() => expect(highlightIn('Runbooks')).not.toBeNull())
    expect(highlightIn('Rules')).toBeNull()
    expect(within(nav).getAllByTestId('nav-highlight')).toHaveLength(1)
  })
})

describe('team layout', () => {
  test('a known slug renders the team page with the team name', async () => {
    const { findByRole, getByRole, getByText } = signedInAs(
      petra('user', [membership(settlements, 'member')]),
      '/teams/settlements/alerts',
    )

    expect(await findByRole('heading', { level: 1, name: 'Alerts' })).toBeInTheDocument()
    expect(getByText('Settlements', { selector: 'header span' })).toBeInTheDocument()
    expect(getByRole('button', { name: 'Team: Settlements. Switch team' })).toBeInTheDocument()
    expect(localStorage.getItem('last-team')).toBe('settlements')
  })

  test('/teams/$team opens the alerts page', async () => {
    const { findByRole, router } = signedInAs(petra('user', [membership(settlements, 'viewer')]), '/teams/settlements')

    expect(await findByRole('heading', { level: 1, name: 'Alerts' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/teams/settlements/alerts')
  })

  test('an unknown slug shows the 404 page inside the shell', async () => {
    const { findByRole, getByRole } = signedInAs(petra('user', [membership(settlements, 'member')]), '/teams/nope/alerts')

    expect(await findByRole('alert')).toHaveTextContent('Page not found')
    expect(getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
  })

  test('an admin opens a team they are not in through GET /teams', async () => {
    server.use(respond(listTeams, 'get', getListTeamsUrl(), 200, [settlements, payments]))
    const { findByRole } = signedInAs(petra('admin', []), '/teams/payments/rules')

    expect(await findByRole('heading', { level: 1, name: 'Rules' })).toBeInTheDocument()
    expect(await findByRole('button', { name: 'Team: Payments. Switch team' })).toBeInTheDocument()
  })

  test('an admin gets the 404 page for a team while GET /teams is a stub', async () => {
    server.use(http.get(getListTeamsUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const { findByRole } = signedInAs(petra('admin', []), '/teams/payments/rules')

    expect(await findByRole('alert')).toHaveTextContent('Page not found')
  })

  test('the overview links to the team opened last', async () => {
    localStorage.setItem('last-team', 'payments')
    const { findByRole } = signedInAs(
      petra('user', [membership(settlements, 'member'), membership(payments, 'member')]),
      '/',
    )

    expect(await findByRole('button', { name: 'Team: Payments. Switch team' })).toBeInTheDocument()
  })

  test('the overview falls back to the first membership', async () => {
    localStorage.setItem('last-team', 'gone')
    const { findByRole } = signedInAs(
      petra('user', [membership(settlements, 'member'), membership(payments, 'member')]),
      '/',
    )

    expect(await findByRole('button', { name: 'Team: Settlements. Switch team' })).toBeInTheDocument()
  })
})

describe('not found and errors', () => {
  test('an unknown path shows the 404 page inside the shell', async () => {
    const { findByRole, getByRole } = signedInAs(petra('user', []), '/no/such/page')

    expect(await findByRole('alert')).toHaveTextContent('Page not found')
    expect(getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
    expect(getByRole('link', { name: 'Go to overview' })).toHaveAttribute('href', '/')
  })

  test('an admin page shows the 404 page to a non-admin', async () => {
    const { findByRole, queryByRole } = signedInAs(petra('user', []), '/admin/users')

    expect(await findByRole('alert')).toHaveTextContent('Page not found')
    expect(queryByRole('heading', { level: 1, name: 'Users' })).not.toBeInTheDocument()
  })

  test('an admin opens the Users page', async () => {
    server.use(respond(listTeams, 'get', getListTeamsUrl(), 200, []))
    const { findByRole, user } = signedInAs(petra('admin', []), '/')

    await user.click(await findByRole('link', { name: 'Users' }))

    expect(await findByRole('heading', { level: 1, name: 'Users' })).toBeInTheDocument()
  })

  test('a screen that throws shows the error inside the shell', async () => {
    const me = petra('user', [])
    const queryClient = new QueryClient()
    const rootRoute = createRootRouteWithContext<RouterContext>()()
    const appRoute = createRoute({ getParentRoute: () => rootRoute, id: '_app', beforeLoad: () => ({ me }), component: AppShell })
    const broken = createRoute({
      getParentRoute: () => appRoute,
      path: '/',
      component: () => {
        throw new Error('render failed')
      },
    })
    const router = createRouter({
      routeTree: rootRoute.addChildren([appRoute.addChildren([broken])]),
      history: createMemoryHistory({ initialEntries: ['/'] }),
      context: { queryClient },
    })
    // React logs the caught render error; the assertion is what the user sees.
    const silence = console.error
    console.error = () => {}
    try {
      const { findByRole, getByRole } = render(
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      )

      expect(await findByRole('alert')).toHaveTextContent("Couldn't show this page")
      expect(getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
      expect(getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    } finally {
      console.error = silence
    }
  })
})

describe('theme toggle', () => {
  test('picking Dark stores the choice and sets data-theme', async () => {
    const { findByRole, user } = signedInAs(petra('user', []), '/')

    await user.click(await findByRole('button', { name: 'Dark' }))

    expect(localStorage.getItem('theme')).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')

    await user.click(await findByRole('button', { name: 'System' }))

    expect(localStorage.getItem('theme')).toBe('system')
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})

describe('navigation sheet', () => {
  test('opens from the header, closes on navigation and returns focus', async () => {
    const { findByRole, user, router } = signedInAs(petra('user', []), '/')
    const trigger = await findByRole('button', { name: 'Open navigation' })

    await user.click(trigger)
    const sheet = await findByRole('dialog', { name: 'Navigation' })
    await user.click(within(sheet).getByRole('link', { name: 'My rules' }))

    await waitFor(() => expect(router.state.location.pathname).toBe('/me/rules'))
    await waitFor(() => expect(within(document.body).queryByRole('dialog')).not.toBeInTheDocument())

    await user.click(trigger)
    await findByRole('dialog', { name: 'Navigation' })
    await user.keyboard('{Escape}')

    await waitFor(() => expect(within(document.body).queryByRole('dialog')).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
  })
})
