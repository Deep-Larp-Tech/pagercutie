import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { waitFor } from '@testing-library/react'
import { getGetMeUrl, getLoginUrl, getMe, login } from '@/api/generated/auth/auth'
import { getGetMeResponseMock } from '@/api/generated/auth/auth.faker'
import { respond } from '@/test/http'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'
import { quietFeedEndpoints } from '@/test/alerts'

beforeEach(() => server.use(...quietFeedEndpoints()))

const me = getGetMeResponseMock({
  user: {
    id: '0193a000-0000-7000-8000-000000000001',
    email: 'anna@example.com',
    display_name: 'Anna Novak',
    phone: null,
    timezone: 'Europe/Prague',
    role: 'user',
    created_at: '2026-01-01T00:00:00Z',
  },
})

function signedOut() {
  server.use(respond(getMe, 'get', getGetMeUrl(), 401, { detail: 'Not signed in.' }))
}

async function signIn(route: string, email = 'anna@example.com') {
  const rendered = renderApp(route)
  await rendered.user.type(await rendered.findByLabelText('Work email'), email)
  await rendered.user.click(rendered.getByRole('button', { name: 'Sign in' }))
  return rendered
}

describe('POST /auth/login', () => {
  test('the heading is the logo, named PagerCutie', async () => {
    signedOut()

    const { findByRole } = renderApp('/login')

    const heading = await findByRole('heading', { level: 1, name: 'PagerCutie' })
    expect(heading.querySelector('svg[role="img"]')).not.toBeNull()
  })

  test('success opens /with the user from the response, without fetching GET /me again', async () => {
    signedOut()
    server.use(respond(login, 'post', getLoginUrl(), 200, me))

    const { findByRole, router } = await signIn('/login')

    expect(await findByRole('button', { name: 'Anna Novak, account menu' })).toBeInTheDocument()
    expect(router.state.location.href).toBe('/')
  })

  test('success opens the redirect target', async () => {
    signedOut()
    server.use(respond(login, 'post', getLoginUrl(), 200, me))
    const target = '/teams/payments/rules?view=mine'

    const { router } = await signIn(`/login?redirect=${encodeURIComponent(target)}`)

    await waitFor(() => expect(router.state.location.href).toBe(target))
  })

  test.each(['//evil.com/teams', 'https://evil.com/teams', '/\\evil.com/teams', 'teams'])(
    'an unsafe redirect %s falls back to /',
    async (target) => {
      signedOut()
      server.use(respond(login, 'post', getLoginUrl(), 200, me))

      const { findByRole, router } = await signIn(`/login?redirect=${encodeURIComponent(target)}`)

      expect(await findByRole('button', { name: 'Anna Novak, account menu' })).toBeInTheDocument()
      expect(router.state.location.href).toBe('/')
    },
  )

  test('404 shows the message under the field', async () => {
    signedOut()
    server.use(respond(login, 'post', getLoginUrl(), 404, { detail: 'No user with that email.' }))

    const { findByText, getByLabelText, router } = await signIn('/login', 'nobody@example.com')

    const message = await findByText('No account with that email. Ask an admin to add you.')
    const input = getByLabelText('Work email')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input.getAttribute('aria-describedby')?.split(' ')).toContain(message.id)
    expect(router.state.location.pathname).toBe('/login')
  })

  test('422 shows the field error from the response', async () => {
    signedOut()
    const msg = 'value is not a valid email address: The domain name example.invalid does not exist.'
    server.use(
      respond(login, 'post', getLoginUrl(), 422, {
        detail: [{ loc: ['body', 'email'], msg, type: 'value_error' }],
      }),
    )

    const { findByText } = await signIn('/login', 'anna@example.invalid')

    expect(await findByText(msg)).toBeInTheDocument()
  })

  test('422 without a field error and 400 fall back to the generic message', async () => {
    signedOut()
    server.use(respond(login, 'post', getLoginUrl(), 422, {}))

    const first = await signIn('/login')
    expect(await first.findByText('Enter a valid email address.')).toBeInTheDocument()
    first.unmount()

    server.use(respond(login, 'post', getLoginUrl(), 400, { detail: 'There was an error parsing the body' }))
    const second = await signIn('/login')
    expect(await second.findByText('Enter a valid email address.')).toBeInTheDocument()
  })

  test('an invalid email is rejected without a request', async () => {
    signedOut()
    const onLogin = vi.fn()
    server.use(http.post(getLoginUrl(), () => onLogin()))

    const { findByText, user, getByLabelText, getByRole } = await signIn('/login', 'not-an-email')
    expect(await findByText('Enter a valid email address.')).toBeInTheDocument()

    await user.clear(getByLabelText('Work email'))
    await user.click(getByRole('button', { name: 'Sign in' }))
    expect(await findByText('Enter your work email.')).toBeInTheDocument()
    expect(onLogin).not.toHaveBeenCalled()
  })

  test('the button shows the pending state while the request runs', async () => {
    signedOut()
    let answer = () => {}
    const answered = new Promise<void>((resolve) => {
      answer = resolve
    })
    server.use(
      http.post(getLoginUrl(), async () => {
        await answered
        return HttpResponse.json(me)
      }),
    )

    const { findByRole } = await signIn('/login')

    expect(await findByRole('button', { name: 'Signing in…' })).toBeDisabled()
    answer()
    expect(await findByRole('button', { name: 'Anna Novak, account menu' })).toBeInTheDocument()
  })

  test('an undocumented status shows the shared fallback', async () => {
    signedOut()
    server.use(http.post(getLoginUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole } = await signIn('/login')

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('a signed-in user opening /login lands on /', async () => {
    server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))

    const { findByRole, router } = renderApp('/login')

    expect(await findByRole('button', { name: 'Anna Novak, account menu' })).toBeInTheDocument()
    expect(router.state.location.href).toBe('/')
  })
})
