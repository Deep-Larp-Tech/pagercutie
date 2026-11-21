import { http, HttpResponse } from 'msw'
import { toast } from 'sonner'
import { afterEach, describe, expect, test } from 'vitest'
import { within } from '@testing-library/react'
import { getGetMeUrl, getMe } from '@/api/generated/auth/auth'
import type { MeRead, UserUpdate } from '@/api/generated/model'
import { getUpdateUserUrl, updateUser } from '@/api/generated/users/users'
import { respond } from '@/test/http'
import { petra } from '@/test/people'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const me = petra('user', [])
const PHONE_FORMAT =
  'Enter the number in international format: a plus sign, the country code and the number, e.g. +420601234567.'

// Sonner keeps toasts in a module-level store, so one test's toast would show in the next.
afterEach(() => {
  toast.dismiss()
})

function openProfile(signedIn: MeRead = me) {
  server.use(respond(getMe, 'get', getGetMeUrl(), 200, signedIn))
  return renderApp('/me/profile')
}

/** The `Field` around the control labelled `label`, to check the error is under the right field. */
function fieldOf(control: HTMLElement): HTMLElement {
  const field = control.closest<HTMLElement>('[data-slot="field"]')
  if (field === null) throw new Error('control is not inside a Field')
  return field
}

describe('/me/profile', () => {
  test('shows the profile with the email read-only and Save disabled until something changes', async () => {
    const { findByLabelText, getByLabelText, getByRole, user } = openProfile()

    const name = await findByLabelText('Display name')
    expect(name).toHaveValue('Petra Dvorak')
    expect(getByLabelText('Email')).toHaveValue('petra@example.com')
    expect(getByLabelText('Email')).toHaveAttribute('readonly')
    expect(getByLabelText('Time zone')).toHaveValue('Europe/Prague')
    expect(getByRole('button', { name: 'Save profile' })).toBeDisabled()

    await user.type(name, 'x')
    expect(getByRole('button', { name: 'Save profile' })).toBeEnabled()
    await user.type(name, '{Backspace}')
    expect(getByRole('button', { name: 'Save profile' })).toBeDisabled()
  })

  test('a phone number that is not E.164 is rejected under the phone field without a request', async () => {
    const { findByLabelText, getByRole, user } = openProfile()

    const phone = await findByLabelText('Phone')
    await user.type(phone, '601 234 567')
    await user.click(getByRole('button', { name: 'Save profile' }))

    expect(await within(fieldOf(phone)).findByText(PHONE_FORMAT)).toBeInTheDocument()
  })

  test('a stored phone number cannot be emptied, because the API cannot clear it', async () => {
    const { findByLabelText, getByRole, user } = openProfile({
      ...me,
      user: { ...me.user, phone: '+420601234567' },
    })

    const phone = await findByLabelText('Phone')
    await user.clear(phone)
    await user.click(getByRole('button', { name: 'Save profile' }))

    expect(
      await within(fieldOf(phone)).findByText("You can't remove a phone number yet. Enter a different number instead."),
    ).toBeInTheDocument()
  })
})

describe('PATCH /users/{id} (self)', () => {
  test('200 sends only the changed field, says so and refreshes the name in the shell', async () => {
    let current = me
    const bodies: UserUpdate[] = []
    server.use(
      http.get(getGetMeUrl(), () => HttpResponse.json(current)),
      http.patch<never, UserUpdate>(getUpdateUserUrl(me.user.id), async ({ request }) => {
        const body = await request.json()
        bodies.push(body)
        current = { ...current, user: { ...current.user, display_name: body.display_name ?? current.user.display_name } }
        return HttpResponse.json(current.user)
      }),
    )
    const { findByLabelText, findByRole, findByText, getByRole, user } = renderApp('/me/profile')

    const name = await findByLabelText('Display name')
    await user.clear(name)
    await user.type(name, 'Petra Novak')
    await user.click(getByRole('button', { name: 'Save profile' }))

    expect(await findByText('Profile saved')).toBeInTheDocument()
    expect(await findByRole('button', { name: 'Petra Novak, account menu' })).toBeInTheDocument()
    expect(bodies).toEqual([{ display_name: 'Petra Novak' }])
    expect(getByRole('button', { name: 'Save profile' })).toBeDisabled()
  })

  test('200 saves a time zone picked from the searchable list', async () => {
    const bodies: UserUpdate[] = []
    server.use(
      http.patch<never, UserUpdate>(getUpdateUserUrl(me.user.id), async ({ request }) => {
        const body = await request.json()
        bodies.push(body)
        return HttpResponse.json({ ...me.user, timezone: body.timezone ?? me.user.timezone })
      }),
    )
    const { findByLabelText, findByRole, findByText, getByRole, user } = openProfile()

    const zone = await findByLabelText('Time zone')
    await user.clear(zone)
    await user.type(zone, 'Tokyo')
    await user.click(await findByRole('option', { name: /Asia\/Tokyo/ }))
    await user.click(getByRole('button', { name: 'Save profile' }))

    expect(await findByText('Profile saved')).toBeInTheDocument()
    expect(bodies).toEqual([{ timezone: 'Asia/Tokyo' }])
  })

  test('422 on the phone shows the message under the phone field', async () => {
    server.use(
      respond(updateUser, 'patch', getUpdateUserUrl(me.user.id), 422, {
        detail: [{ loc: ['body', 'phone'], msg: "String should match pattern '^\\+[1-9]\\d{6,14}$'", type: 'string_pattern_mismatch' }],
      }),
    )
    const { findByLabelText, getByRole, user } = openProfile()

    const phone = await findByLabelText('Phone')
    await user.type(phone, '+42060123')
    await user.click(getByRole('button', { name: 'Save profile' }))

    expect(await within(fieldOf(phone)).findByText(PHONE_FORMAT)).toBeInTheDocument()
  })

  test('403 explains that only the owner or an admin can change the profile', async () => {
    server.use(respond(updateUser, 'patch', getUpdateUserUrl(me.user.id), 403, { detail: 'Not allowed.' }))
    const { findByLabelText, findByRole, getByRole, user } = openProfile()

    await user.type(await findByLabelText('Display name'), ' Jr')
    await user.click(getByRole('button', { name: 'Save profile' }))

    expect(await findByRole('alert')).toHaveTextContent(
      "You can't change this profile. Only its owner or an admin can.",
    )
  })

  test('an undocumented status such as the 501 stub falls back to the shared message', async () => {
    server.use(http.patch(getUpdateUserUrl(me.user.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    const { findByLabelText, findByRole, getByRole, user } = openProfile()

    await user.type(await findByLabelText('Display name'), ' Jr')
    await user.click(getByRole('button', { name: 'Save profile' }))

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})
