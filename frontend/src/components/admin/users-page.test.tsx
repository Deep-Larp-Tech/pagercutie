import { delay, http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import type { UserRead } from '@/api/generated/model'
import {
  createUser,
  deleteUser,
  getCreateUserUrl,
  getDeleteUserUrl,
  getGetUserUrl,
  getListUsersUrl,
  getUpdateUserUrl,
  getUser,
  listUsers,
  updateUser,
} from '@/api/generated/users/users'
import { Toaster } from '@/components/ui/sonner'
import { respond } from '@/test/http'
import { petra } from '@/test/people'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { UsersPage } from './users-page'

const me = petra('admin', [])

function user(id: string, name: string, overrides: Partial<UserRead> = {}): UserRead {
  return {
    id,
    email: `${name.split(' ')[0]?.toLowerCase()}@example.com`,
    display_name: name,
    phone: null,
    timezone: 'Europe/Prague',
    role: 'user',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

const anna = user('0193a000-0000-7000-8000-000000000001', 'Anna Novak', { phone: '+420601234567' })
const self = me.user

let events: ReturnType<typeof renderWithProviders>['user'] | undefined

/** Renders the page with the toaster, as the root layout does; later helpers drive it with the same user. */
function setup() {
  const rendered = renderWithProviders(
    <>
      <UsersPage />
      <Toaster />
    </>,
    { route: '/admin/users', me },
  )
  events = rendered.user
  return rendered
}

function userEvents() {
  if (events === undefined) throw new Error('call setup() first')
  return events
}

function listing(users: UserRead[]) {
  return respond(listUsers, 'get', getListUsersUrl(), 200, users)
}

async function openRowAction(name: string, action: string) {
  await userEvents().click(await screen.findByRole('button', { name: `Actions for ${name}` }))
  await userEvents().click(await screen.findByRole('menuitem', { name: action }))
}

/** The error text under the field labelled `label`. */
function fieldError(dialog: HTMLElement, label: string) {
  const field = within(dialog).getByText(label, { selector: 'label' }).closest('[data-slot="field"]')
  if (!(field instanceof HTMLElement)) throw new Error(`no field labelled ${label}`)
  return within(field).getByText((_, element) => element?.getAttribute('data-slot') === 'field-error')
}

describe('GET /users', () => {
  test('lists every user with email and global role, and marks the signed-in admin', async () => {
    server.use(listing([anna, user(self.id, self.display_name, { role: 'admin', email: self.email })]))
    setup()

    await screen.findByText('Anna Novak')
    const rows = within(screen.getByRole('table', { name: 'Users' })).getAllByRole('row')
    expect(rows.map((row) => row.textContent)).toEqual([
      'NameEmailGlobal roleActions',
      'Anna Novakanna@example.comUser',
      'Petra Dvorak(you)petra@example.comAdmin',
    ])
  })

  test('shows skeleton rows while loading', async () => {
    server.use(http.get(getListUsersUrl(), () => delay('infinite')))
    setup()

    expect(await screen.findAllByTestId('skeleton-row')).toHaveLength(5)
    expect(screen.getByRole('table', { name: 'Users' })).toHaveAttribute('aria-busy', 'true')
  })

  test('shows an empty state when there are no users', async () => {
    server.use(listing([]))
    setup()

    expect(await screen.findByText('No users yet')).toBeInTheDocument()
  })

  test('422 shows the error state with Try again', async () => {
    server.use(respond(listUsers, 'get', getListUsersUrl(), 422, { detail: [] }))
    setup()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent("Couldn't load users")
    expect(alert).toHaveTextContent('The list request was not valid. Reload the page and try again.')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  test('403, which the list does not document, falls back to the shared message', async () => {
    server.use(http.get(getListUsersUrl(), () => HttpResponse.json({ detail: 'Admins only' }, { status: 403 })))
    setup()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Something went wrong on the server (HTTP 403). Try again in a moment.',
    )
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(http.get(getListUsersUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    setup()

    expect(await screen.findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('a full page of 100 offers Show more, which loads the next page', async () => {
    const firstPage = Array.from({ length: 100 }, (_, index) =>
      user(`0193a000-0000-7000-8000-${String(index).padStart(12, '0')}`, `User ${index}`),
    )
    const offsets: string[] = []
    server.use(
      http.get(getListUsersUrl(), ({ request }) => {
        const params = new URL(request.url).searchParams
        offsets.push(`${params.get('limit')}/${params.get('offset')}`)
        return HttpResponse.json(params.get('offset') === '0' ? firstPage : [anna])
      }),
    )
    setup()

    await userEvents().click(await screen.findByRole('button', { name: 'Show more' }))

    expect(await screen.findByText('Anna Novak')).toBeInTheDocument()
    expect(within(screen.getByRole('table', { name: 'Users' })).getAllByRole('row')).toHaveLength(102)
    expect(offsets).toEqual(['100/0', '100/100'])
    expect(screen.queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument()
  })

  test('an admin cannot delete themselves: their row has no Delete user', async () => {
    server.use(listing([anna, user(self.id, self.display_name, { role: 'admin' })]))
    setup()

    await userEvents().click(await screen.findByRole('button', { name: `Actions for ${self.display_name}` }))
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Edit user' })).toBeInTheDocument()
    expect(within(menu).queryByRole('menuitem', { name: 'Delete user' })).not.toBeInTheDocument()
  })
})

describe('POST /users', () => {
  async function openAddUser() {
    await userEvents().click(await screen.findByRole('button', { name: 'Add user' }))
    return screen.findByRole('dialog', { name: 'Add user' })
  }

  async function fill(dialog: HTMLElement, email = 'anna@example.com', name = 'Anna Novak') {
    await userEvents().type(within(dialog).getByLabelText('Email'), email)
    await userEvents().type(within(dialog).getByLabelText('Name'), name)
  }

  test('creates the user, closes the dialog, refreshes the list and confirms with a toast', async () => {
    let body: unknown
    let listCalls = 0
    server.use(
      http.get(getListUsersUrl(), () => {
        listCalls += 1
        return HttpResponse.json(listCalls === 1 ? [] : [anna])
      }),
      http.post(getCreateUserUrl(), async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(anna, { status: 201 })
      }),
    )
    setup()
    const dialog = await openAddUser()

    await fill(dialog)
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add user' }))

    expect(await screen.findByText('Anna Novak added')).toBeInTheDocument()
    // An empty phone goes out as null; the time zone defaults to the browser's.
    expect(body).toEqual({
      email: 'anna@example.com',
      display_name: 'Anna Novak',
      phone: null,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      role: 'user',
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByRole('cell', { name: 'Anna Novak' })).toBeInTheDocument()
  })

  test('a phone number that is not E.164 is rejected before sending', async () => {
    server.use(listing([]))
    setup()
    const dialog = await openAddUser()

    await fill(dialog)
    await userEvents().type(within(dialog).getByLabelText('Phone'), '601 234 567')
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add user' }))

    expect(fieldError(dialog, 'Phone')).toHaveTextContent(
      'Enter the number in international format, for example +420601234567.',
    )
  })

  test('409 shows the duplicate email under Email', async () => {
    server.use(
      listing([]),
      respond(createUser, 'post', getCreateUserUrl(), 409, { detail: 'Email already registered' }),
    )
    setup()
    const dialog = await openAddUser()

    await fill(dialog)
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add user' }))

    await waitFor(() =>
      expect(fieldError(dialog, 'Email')).toHaveTextContent(
        'A user with this email already exists. Use another email.',
      ),
    )
  })

  test('422 puts each error under the field its loc names', async () => {
    server.use(
      listing([]),
      respond(createUser, 'post', getCreateUserUrl(), 422, {
        detail: [
          { loc: ['body', 'display_name'], msg: 'Name is reserved', type: 'value_error' },
          { loc: ['body', 'timezone'], msg: 'Unknown time zone', type: 'value_error' },
        ],
      }),
    )
    setup()
    const dialog = await openAddUser()

    await fill(dialog)
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add user' }))

    await waitFor(() => expect(fieldError(dialog, 'Name')).toHaveTextContent('Name is reserved'))
    expect(fieldError(dialog, 'Time zone')).toHaveTextContent('Unknown time zone')
  })

  test('403 says only admins can add users', async () => {
    server.use(listing([]), respond(createUser, 'post', getCreateUserUrl(), 403, { detail: 'Forbidden' }))
    setup()
    const dialog = await openAddUser()

    await fill(dialog)
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add user' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Only admins can add users.')
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(
      listing([]),
      http.post(getCreateUserUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    setup()
    const dialog = await openAddUser()

    await fill(dialog)
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add user' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('GET /users/{id}', () => {
  test('the edit form starts from the stored user, not the list row', async () => {
    server.use(
      listing([anna]),
      respond(getUser, 'get', getGetUserUrl(anna.id), 200, { ...anna, display_name: 'Anna Svobodova' }),
    )
    setup()

    await openRowAction('Anna Novak', 'Edit user')
    const dialog = await screen.findByRole('dialog', { name: 'Edit user' })

    expect(await within(dialog).findByLabelText('Name')).toHaveValue('Anna Svobodova')
    expect(within(dialog).getByLabelText('Phone')).toHaveValue('+420601234567')
  })

  test('404 says the user no longer exists', async () => {
    server.use(listing([anna]), respond(getUser, 'get', getGetUserUrl(anna.id), 404, { detail: 'Not found' }))
    setup()

    await openRowAction('Anna Novak', 'Edit user')

    expect(await screen.findByRole('alert')).toHaveTextContent('This user no longer exists.')
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(
      listing([anna]),
      http.get(getGetUserUrl(anna.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    setup()

    await openRowAction('Anna Novak', 'Edit user')

    expect(await screen.findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('PATCH /users/{id}', () => {
  async function openEdit() {
    await openRowAction('Anna Novak', 'Edit user')
    const dialog = await screen.findByRole('dialog', { name: 'Edit user' })
    await within(dialog).findByLabelText('Name')
    return dialog
  }

  async function rename(dialog: HTMLElement, name = 'Anna Svobodova') {
    const input = within(dialog).getByLabelText('Name')
    await userEvents().clear(input)
    await userEvents().type(input, name)
    await userEvents().click(within(dialog).getByRole('button', { name: 'Save changes' }))
  }

  test('sends only the changed fields and confirms with a toast', async () => {
    let body: unknown
    server.use(
      listing([anna]),
      respond(getUser, 'get', getGetUserUrl(anna.id), 200, anna),
      http.patch(getUpdateUserUrl(anna.id), async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ...anna, display_name: 'Anna Svobodova' })
      }),
    )
    setup()
    const dialog = await openEdit()

    await rename(dialog)

    expect(await screen.findByText('Changes to Anna Svobodova saved')).toBeInTheDocument()
    expect(body).toEqual({ display_name: 'Anna Svobodova' })
  })

  test('emptying the phone says it cannot be removed and sends nothing', async () => {
    server.use(listing([anna]), respond(getUser, 'get', getGetUserUrl(anna.id), 200, anna))
    setup()
    const dialog = await openEdit()

    await userEvents().clear(within(dialog).getByLabelText('Phone'))
    await userEvents().click(within(dialog).getByRole('button', { name: 'Save changes' }))

    expect(fieldError(dialog, 'Phone')).toHaveTextContent("A phone number can't be removed yet.")
  })

  test('422 puts the error under the field its loc names', async () => {
    server.use(
      listing([anna]),
      respond(getUser, 'get', getGetUserUrl(anna.id), 200, anna),
      respond(updateUser, 'patch', getUpdateUserUrl(anna.id), 422, {
        detail: [{ loc: ['body', 'display_name'], msg: 'Name is reserved', type: 'value_error' }],
      }),
    )
    setup()
    const dialog = await openEdit()

    await rename(dialog)

    await waitFor(() => expect(fieldError(dialog, 'Name')).toHaveTextContent('Name is reserved'))
  })

  test('403 says only admins can change other users', async () => {
    server.use(
      listing([anna]),
      respond(getUser, 'get', getGetUserUrl(anna.id), 200, anna),
      respond(updateUser, 'patch', getUpdateUserUrl(anna.id), 403, { detail: 'Forbidden' }),
    )
    setup()
    const dialog = await openEdit()

    await rename(dialog)

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Only admins can change other users.')
  })

  test('404 says the user no longer exists', async () => {
    server.use(
      listing([anna]),
      respond(getUser, 'get', getGetUserUrl(anna.id), 200, anna),
      respond(updateUser, 'patch', getUpdateUserUrl(anna.id), 404, { detail: 'Not found' }),
    )
    setup()
    const dialog = await openEdit()

    await rename(dialog)

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This user no longer exists.')
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(
      listing([anna]),
      respond(getUser, 'get', getGetUserUrl(anna.id), 200, anna),
      http.patch(getUpdateUserUrl(anna.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    setup()
    const dialog = await openEdit()

    await rename(dialog)

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('DELETE /users/{id}', () => {
  async function confirmDelete() {
    await openRowAction('Anna Novak', 'Delete user')
    const dialog = await screen.findByRole('alertdialog', { name: 'Delete Anna Novak?' })
    await userEvents().click(within(dialog).getByRole('button', { name: 'Delete user' }))
    return dialog
  }

  test('asks with the user named, deletes, and confirms with a toast', async () => {
    let listCalls = 0
    server.use(
      http.get(getListUsersUrl(), () => {
        listCalls += 1
        return HttpResponse.json(listCalls === 1 ? [anna] : [])
      }),
      respond(deleteUser, 'delete', getDeleteUserUrl(anna.id), 204, undefined),
    )
    setup()

    await confirmDelete()

    expect(await screen.findByText('Anna Novak deleted')).toBeInTheDocument()
    expect(await screen.findByText('No users yet')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
  })

  test('403 says only admins can delete users', async () => {
    server.use(listing([anna]), respond(deleteUser, 'delete', getDeleteUserUrl(anna.id), 403, { detail: 'No' }))
    setup()

    const dialog = await confirmDelete()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Only admins can delete users.')
  })

  test('404 says the user no longer exists', async () => {
    server.use(listing([anna]), respond(deleteUser, 'delete', getDeleteUserUrl(anna.id), 404, { detail: 'No' }))
    setup()

    const dialog = await confirmDelete()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This user no longer exists.')
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(
      listing([anna]),
      http.delete(getDeleteUserUrl(anna.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    setup()

    const dialog = await confirmDelete()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})
