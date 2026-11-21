import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { getGetMeUrl, getLogoutUrl, getMe, logout } from '@/api/generated/auth/auth'
import { getGetMeResponseMock } from '@/api/generated/auth/auth.faker'
import { respond } from '@/test/http'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

async function renderSignedIn() {
  server.use(respond(getMe, 'get', getGetMeUrl(), 200, getGetMeResponseMock()))
  const rendered = renderApp('/')
  await rendered.findByText(/Signed in as/)
  rendered.queryClient.setQueryData(['cached', 'by', 'another', 'screen'], 'stale')
  return rendered
}

describe('POST /auth/logout', () => {
  test('204 clears the cache and lands on /login', async () => {
    const { user, getByRole, findByLabelText, queryClient, router } = await renderSignedIn()
    server.use(
      respond(logout, 'post', getLogoutUrl(), 204, undefined),
      respond(getMe, 'get', getGetMeUrl(), 401, { detail: 'Not signed in.' }),
    )

    await user.click(getByRole('button', { name: 'Sign out' }))

    expect(await findByLabelText('Work email')).toBeInTheDocument()
    expect(router.state.location.href).toBe('/login')
    expect(queryClient.getQueryData(['cached', 'by', 'another', 'screen'])).toBeUndefined()
  })

  test('an undocumented status keeps the user signed in and explains', async () => {
    const { user, getByRole, findByRole, router } = await renderSignedIn()
    server.use(http.post(getLogoutUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 500 })))

    await user.click(getByRole('button', { name: 'Sign out' }))

    expect(await findByRole('alert')).toHaveTextContent(
      'Something went wrong on the server (HTTP 500). Try again in a moment.',
    )
    expect(router.state.location.href).toBe('/')
  })
})
