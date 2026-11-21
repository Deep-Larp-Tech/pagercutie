import { delay, http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import type { TeamRead } from '@/api/generated/model'
import {
  createTeam,
  deleteTeam,
  getCreateTeamUrl,
  getDeleteTeamUrl,
  getListTeamsUrl,
  getUpdateTeamUrl,
  listTeams,
  updateTeam,
} from '@/api/generated/teams/teams'
import { Toaster } from '@/components/ui/sonner'
import { meQueryOptions } from '@/lib/session'
import { adminTeamsQueryOptions } from '@/lib/teams'
import { respond } from '@/test/http'
import { membership, petra, team } from '@/test/people'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import { TeamsPage } from './teams-page'

const payments: TeamRead = { ...team('payments', 'Payments'), description: 'Card and bank payments' }
const me = petra('admin', [membership(payments, 'lead')])

let events: ReturnType<typeof renderWithProviders>['user'] | undefined

/** Renders the page with the toaster, as the root layout does; later helpers drive it with the same user. */
function setup() {
  const rendered = renderWithProviders(
    <>
      <TeamsPage />
      <Toaster />
    </>,
    { route: '/admin/teams', me },
  )
  events = rendered.user
  return rendered
}

function userEvents() {
  if (events === undefined) throw new Error('call setup() first')
  return events
}

function listing(teams: TeamRead[]) {
  return respond(listTeams, 'get', getListTeamsUrl(), 200, teams)
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

describe('GET /teams', () => {
  test('lists every team with slug and description, the name linking to its alerts', async () => {
    server.use(listing([payments]))
    setup()

    const link = await screen.findByRole('link', { name: 'Payments' })
    expect(link).toHaveAttribute('href', '/teams/payments/alerts')
    const row = link.closest('tr')
    if (row === null) throw new Error('no row')
    expect(row).toHaveTextContent('paymentsCard and bank payments')
  })

  test('shows skeleton rows while loading', async () => {
    server.use(http.get(getListTeamsUrl(), () => delay('infinite')))
    setup()

    expect(await screen.findAllByTestId('skeleton-row')).toHaveLength(5)
  })

  test('shows an empty state when there are no teams', async () => {
    server.use(listing([]))
    setup()

    expect(await screen.findByText('No teams yet')).toBeInTheDocument()
  })

  test('422 shows the error state', async () => {
    server.use(respond(listTeams, 'get', getListTeamsUrl(), 422, { detail: [] }))
    setup()

    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load teams")
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(http.get(getListTeamsUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))
    setup()

    expect(await screen.findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('403, which the list does not document, falls back to the shared message', async () => {
    server.use(http.get(getListTeamsUrl(), () => HttpResponse.json({ detail: 'No' }, { status: 403 })))
    setup()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Something went wrong on the server (HTTP 403). Try again in a moment.',
    )
  })

  test('a failed Show more keeps the loaded teams and says why', async () => {
    const firstPage = Array.from({ length: 100 }, (_, index) => team(`team-${index}`, `Team ${index}`))
    server.use(
      http.get(getListTeamsUrl(), ({ request }) =>
        new URL(request.url).searchParams.get('offset') === '0'
          ? HttpResponse.json(firstPage)
          : HttpResponse.json({ detail: [] }, { status: 422 }),
      ),
    )
    setup()

    await userEvents().click(await screen.findByRole('button', { name: 'Show more' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The list request was not valid.')
    expect(screen.getByRole('link', { name: 'Team 99' })).toBeInTheDocument()
  })
})

describe('POST /teams', () => {
  async function openAddTeam() {
    await userEvents().click(await screen.findByRole('button', { name: 'Add team' }))
    return screen.findByRole('dialog', { name: 'Add team' })
  }

  test('derives the slug from the name until the slug is edited', async () => {
    server.use(listing([]))
    setup()
    const dialog = await openAddTeam()
    const name = within(dialog).getByLabelText('Name')
    const slug = within(dialog).getByLabelText('Slug')

    await userEvents().type(name, 'Účty a Platby!')
    expect(slug).toHaveValue('ucty-a-platby')

    await userEvents().clear(slug)
    await userEvents().type(slug, 'accounts')
    await userEvents().type(name, ' 2')
    expect(slug).toHaveValue('accounts')
  })

  test('rejects a slug that does not match the pattern before sending', async () => {
    server.use(listing([]))
    setup()
    const dialog = await openAddTeam()

    await userEvents().type(within(dialog).getByLabelText('Name'), 'Payments')
    await userEvents().clear(within(dialog).getByLabelText('Slug'))
    await userEvents().type(within(dialog).getByLabelText('Slug'), 'Pay_ments')
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add team' }))

    expect(fieldError(dialog, 'Slug')).toHaveTextContent(
      'Use lower case letters and digits, joined by single hyphens, at most 50 characters.',
    )
  })

  test('creates the team and confirms with a toast', async () => {
    let body: unknown
    server.use(
      listing([]),
      http.post(getCreateTeamUrl(), async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(payments, { status: 201 })
      }),
    )
    const { queryClient } = setup()
    queryClient.setQueryData(adminTeamsQueryOptions.queryKey, { status: 200, data: [], headers: new Headers() })
    const dialog = await openAddTeam()

    await userEvents().type(within(dialog).getByLabelText('Name'), 'Payments')
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add team' }))

    expect(await screen.findByText('Payments added')).toBeInTheDocument()
    expect(body).toEqual({ name: 'Payments', slug: 'payments', description: null })
    expect(queryClient.getQueryState(adminTeamsQueryOptions.queryKey)?.isInvalidated).toBe(true)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('409 shows the duplicate slug under Slug', async () => {
    server.use(listing([]), respond(createTeam, 'post', getCreateTeamUrl(), 409, { detail: 'Slug taken' }))
    setup()
    const dialog = await openAddTeam()

    await userEvents().type(within(dialog).getByLabelText('Name'), 'Payments')
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add team' }))

    await waitFor(() =>
      expect(fieldError(dialog, 'Slug')).toHaveTextContent('Another team already uses this slug. Pick another one.'),
    )
  })

  test('422 puts the error under the field its loc names', async () => {
    server.use(
      listing([]),
      respond(createTeam, 'post', getCreateTeamUrl(), 422, {
        detail: [{ loc: ['body', 'name'], msg: 'Name is reserved', type: 'value_error' }],
      }),
    )
    setup()
    const dialog = await openAddTeam()

    await userEvents().type(within(dialog).getByLabelText('Name'), 'Payments')
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add team' }))

    await waitFor(() => expect(fieldError(dialog, 'Name')).toHaveTextContent('Name is reserved'))
  })

  test('403 says only admins can add teams', async () => {
    server.use(listing([]), respond(createTeam, 'post', getCreateTeamUrl(), 403, { detail: 'No' }))
    setup()
    const dialog = await openAddTeam()

    await userEvents().type(within(dialog).getByLabelText('Name'), 'Payments')
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add team' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Only admins can add teams.')
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(
      listing([]),
      http.post(getCreateTeamUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    setup()
    const dialog = await openAddTeam()

    await userEvents().type(within(dialog).getByLabelText('Name'), 'Payments')
    await userEvents().click(within(dialog).getByRole('button', { name: 'Add team' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('PATCH /teams/{id}', () => {
  async function rename() {
    await openRowAction('Payments', 'Edit team')
    const dialog = await screen.findByRole('dialog', { name: 'Edit team' })
    const name = within(dialog).getByLabelText('Name')
    await userEvents().clear(name)
    await userEvents().type(name, 'Card payments')
    await userEvents().click(within(dialog).getByRole('button', { name: 'Save changes' }))
    return dialog
  }

  test('sends only the changed fields, marks GET /me stale and confirms with a toast', async () => {
    let body: unknown
    server.use(
      listing([payments]),
      http.patch(getUpdateTeamUrl(payments.id), async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ...payments, name: 'Card payments' })
      }),
    )
    const { queryClient } = setup()

    await rename()

    expect(await screen.findByText('Changes to Card payments saved')).toBeInTheDocument()
    expect(body).toEqual({ name: 'Card payments' })
    expect(queryClient.getQueryState(meQueryOptions.queryKey)?.isInvalidated).toBe(true)
  })

  test('emptying the description says it cannot be removed and sends nothing', async () => {
    server.use(listing([payments]))
    setup()
    await openRowAction('Payments', 'Edit team')
    const dialog = await screen.findByRole('dialog', { name: 'Edit team' })

    await userEvents().clear(within(dialog).getByLabelText('Description'))
    await userEvents().click(within(dialog).getByRole('button', { name: 'Save changes' }))

    expect(fieldError(dialog, 'Description')).toHaveTextContent("A description can't be removed yet.")
  })

  test('422 puts the error under the field its loc names', async () => {
    server.use(
      listing([payments]),
      respond(updateTeam, 'patch', getUpdateTeamUrl(payments.id), 422, {
        detail: [{ loc: ['body', 'name'], msg: 'Name is reserved', type: 'value_error' }],
      }),
    )
    setup()

    const dialog = await rename()

    await waitFor(() => expect(fieldError(dialog, 'Name')).toHaveTextContent('Name is reserved'))
  })

  test('403 says who can change the team', async () => {
    server.use(listing([payments]), respond(updateTeam, 'patch', getUpdateTeamUrl(payments.id), 403, { detail: 'No' }))
    setup()

    const dialog = await rename()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'Only admins and team leads can change this team.',
    )
  })

  test('404 says the team no longer exists', async () => {
    server.use(listing([payments]), respond(updateTeam, 'patch', getUpdateTeamUrl(payments.id), 404, { detail: 'No' }))
    setup()

    const dialog = await rename()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This team no longer exists.')
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(
      listing([payments]),
      http.patch(getUpdateTeamUrl(payments.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    setup()

    const dialog = await rename()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('DELETE /teams/{id}', () => {
  async function confirmDelete() {
    await openRowAction('Payments', 'Delete team')
    const dialog = await screen.findByRole('alertdialog', { name: 'Delete Payments?' })
    await userEvents().click(within(dialog).getByRole('button', { name: 'Delete team' }))
    return dialog
  }

  test('asks with the team named, deletes, and confirms with a toast', async () => {
    server.use(listing([payments]), respond(deleteTeam, 'delete', getDeleteTeamUrl(payments.id), 204, undefined))
    setup()

    await confirmDelete()

    expect(await screen.findByText('Payments deleted')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
  })

  test('409 shows the server reason inline', async () => {
    server.use(
      listing([payments]),
      respond(deleteTeam, 'delete', getDeleteTeamUrl(payments.id), 409, {
        detail: 'The team still owns 2 sources and 5 rules.',
      }),
    )
    setup()

    const dialog = await confirmDelete()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('The team still owns 2 sources and 5 rules.')
  })

  test('403 says only admins can delete teams', async () => {
    server.use(listing([payments]), respond(deleteTeam, 'delete', getDeleteTeamUrl(payments.id), 403, { detail: 'No' }))
    setup()

    const dialog = await confirmDelete()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Only admins can delete teams.')
  })

  test('404 says the team no longer exists', async () => {
    server.use(listing([payments]), respond(deleteTeam, 'delete', getDeleteTeamUrl(payments.id), 404, { detail: 'No' }))
    setup()

    const dialog = await confirmDelete()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This team no longer exists.')
  })

  test('the 501 stub says the feature is not available yet', async () => {
    server.use(
      listing([payments]),
      http.delete(getDeleteTeamUrl(payments.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )
    setup()

    const dialog = await confirmDelete()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})
