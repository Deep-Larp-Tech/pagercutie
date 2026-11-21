import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { getGetMeUrl, getLogoutUrl, getMe, logout } from '@/api/generated/auth/auth'
import { respond } from '@/test/http'
import { petra } from '@/test/people'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const me = petra('user', [])

async function openUserMenu() {
  server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
  const rendered = renderApp('/')
  await rendered.user.click(await rendered.findByRole('button', { name: 'Petra Dvorak, account menu' }))
  rendered.queryClient.setQueryData(['cached', 'by', 'another', 'screen'], 'stale')
  return rendered
}

describe('user menu', () => {
  test('shows the name and email and links to the profile', async () => {
    const { findByRole, findByText, user, router } = await openUserMenu()

    expect(await findByText('petra@example.com')).toBeInTheDocument()
    await user.click(await findByRole('menuitem', { name: 'Profile' }))

    expect(router.state.location.pathname).toBe('/me/profile')
  })
})

describe('POST /auth/logout', () => {
  test('204 clears the cache and lands on /login', async () => {
    const { user, findByRole, findByLabelText, queryClient, router } = await openUserMenu()
    server.use(
      respond(logout, 'post', getLogoutUrl(), 204, undefined),
      respond(getMe, 'get', getGetMeUrl(), 401, { detail: 'Not signed in.' }),
    )

    await user.click(await findByRole('menuitem', { name: 'Sign out' }))

    expect(await findByLabelText('Work email')).toBeInTheDocument()
    expect(router.state.location.href).toBe('/login')
    expect(queryClient.getQueryData(['cached', 'by', 'another', 'screen'])).toBeUndefined()
  })

  test('401 counts as signed out', async () => {
    const { user, findByRole, findByLabelText, router } = await openUserMenu()
    server.use(
      respond(logout, 'post', getLogoutUrl(), 401, { detail: 'Not signed in.' }),
      respond(getMe, 'get', getGetMeUrl(), 401, { detail: 'Not signed in.' }),
    )

    await user.click(await findByRole('menuitem', { name: 'Sign out' }))

    expect(await findByLabelText('Work email')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
  })

  test('an undocumented status keeps the user signed in and explains in the menu', async () => {
    const { user, findByRole, router } = await openUserMenu()
    server.use(http.post(getLogoutUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 500 })))

    await user.click(await findByRole('menuitem', { name: 'Sign out' }))

    expect(await findByRole('alert')).toHaveTextContent(
      'Something went wrong on the server (HTTP 500). Try again in a moment.',
    )
    expect(router.state.location.href).toBe('/')
  })
})
