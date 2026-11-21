import { delay, http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { waitFor } from '@testing-library/react'
import { getGetMeUrl } from '@/api/generated/auth/auth'
import { getGetTeamUrl, getTeam, getUpdateTeamUrl, updateTeam } from '@/api/generated/teams/teams'
import { respond } from '@/test/http'
import { server } from '@/test/server'
import { openAs, petraIn, recordRequests, settlements } from '@/test/teams'

const PATH = '/teams/settlements/settings/general'
const described = { ...settlements, description: 'Payouts and settlement workflows' }

describe('GET /teams/{id} on the General page', () => {
  test('a lead sees the name and description in a form', async () => {
    server.use(respond(getTeam, 'get', getGetTeamUrl(settlements.id), 200, described))

    const { findByLabelText, getByLabelText, getByRole, queryByText } = openAs(petraIn('lead'), PATH)

    expect(await findByLabelText('Name')).toHaveValue('Settlements')
    expect(getByLabelText('Description')).toHaveValue('Payouts and settlement workflows')
    expect(getByRole('button', { name: 'Save changes' })).toBeInTheDocument()
    expect(queryByText('Only team leads can change this.')).not.toBeInTheDocument()
  })

  test('shows a skeleton while loading', async () => {
    server.use(
      http.get(getGetTeamUrl(settlements.id), async () => {
        await delay('infinite')
        return HttpResponse.json(described)
      }),
    )

    const { findByTestId } = openAs(petraIn('lead'), PATH)

    expect(await findByTestId('section-skeleton')).toBeInTheDocument()
  })

  test('a member sees the values read-only with one line saying who can change them', async () => {
    server.use(respond(getTeam, 'get', getGetTeamUrl(settlements.id), 200, described))

    const { findByText, queryByRole, queryByLabelText } = openAs(petraIn('member'), PATH)

    expect(await findByText('Payouts and settlement workflows')).toBeInTheDocument()
    expect(await findByText('Only team leads can change this.')).toBeInTheDocument()
    expect(queryByLabelText('Name')).not.toBeInTheDocument()
    expect(queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
  })

  test('404 says the team is gone', async () => {
    server.use(respond(getTeam, 'get', getGetTeamUrl(settlements.id), 404, { detail: 'Not found' }))

    const { findByRole } = openAs(petraIn('lead'), PATH)

    expect(await findByRole('alert')).toHaveTextContent(
      'This team no longer exists. Pick another team from the switcher.',
    )
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(http.get(getGetTeamUrl(settlements.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole } = openAs(petraIn('lead'), PATH)

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('an undocumented 403 shows the shared fallback', async () => {
    server.use(http.get(getGetTeamUrl(settlements.id), () => HttpResponse.json({ detail: 'x' }, { status: 403 })))

    const { findByRole } = openAs(petraIn('lead'), PATH)

    expect(await findByRole('alert')).toHaveTextContent('Something went wrong on the server (HTTP 403).')
  })
})

describe('PATCH /teams/{id} on the General page', () => {
  test('200 saves the fields, says so and reloads GET /me for the team switcher', async () => {
    const renamed = { ...described, name: 'Settlements EU' }
    server.use(
      respond(getTeam, 'get', getGetTeamUrl(settlements.id), 200, described),
      respond(updateTeam, 'patch', getUpdateTeamUrl(settlements.id), 200, renamed),
    )
    const patches = recordRequests('patch', getUpdateTeamUrl(settlements.id))
    const meRequests = recordRequests('get', getGetMeUrl())

    const { findByLabelText, getByRole, findByText, user } = openAs(petraIn('lead'), PATH)
    const name = await findByLabelText('Name')
    await user.clear(name)
    await user.type(name, 'Settlements EU')
    const meRequestsBefore = meRequests.length
    await user.click(getByRole('button', { name: 'Save changes' }))

    expect(await findByText('Team settings saved')).toBeInTheDocument()
    await waitFor(() =>
      expect(patches.map(({ body }) => body)).toEqual([
        { name: 'Settlements EU', description: 'Payouts and settlement workflows' },
      ]),
    )
    await waitFor(() => expect(meRequests.length).toBeGreaterThan(meRequestsBefore))
  })

  test('403 says only leads can change it', async () => {
    server.use(
      respond(getTeam, 'get', getGetTeamUrl(settlements.id), 200, described),
      respond(updateTeam, 'patch', getUpdateTeamUrl(settlements.id), 403, { detail: 'Forbidden' }),
    )

    const { findByRole, user } = openAs(petraIn('lead'), PATH)
    await user.click(await findByRole('button', { name: 'Save changes' }))

    expect(await findByRole('alert')).toHaveTextContent('Only team leads can change this.')
  })

  test('422 shows the message under the field it names', async () => {
    server.use(
      respond(getTeam, 'get', getGetTeamUrl(settlements.id), 200, described),
      respond(updateTeam, 'patch', getUpdateTeamUrl(settlements.id), 422, {
        detail: [{ loc: ['body', 'name'], msg: 'String should have at most 100 characters', type: 'string_too_long' }],
      }),
    )

    const { findByRole, findByText, user } = openAs(petraIn('lead'), PATH)
    await user.click(await findByRole('button', { name: 'Save changes' }))

    const error = await findByText('String should have at most 100 characters')
    expect(error).toHaveAttribute('data-slot', 'field-error')
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(
      respond(getTeam, 'get', getGetTeamUrl(settlements.id), 200, described),
      http.patch(getUpdateTeamUrl(settlements.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )

    const { findByRole, user } = openAs(petraIn('lead'), PATH)
    await user.click(await findByRole('button', { name: 'Save changes' }))

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('an empty name is caught before sending', async () => {
    server.use(respond(getTeam, 'get', getGetTeamUrl(settlements.id), 200, described))
    const patches = recordRequests('patch', getUpdateTeamUrl(settlements.id))

    const { findByLabelText, getByRole, findByText, user } = openAs(petraIn('lead'), PATH)
    await user.clear(await findByLabelText('Name'))
    await user.click(getByRole('button', { name: 'Save changes' }))

    expect(await findByText('Enter a team name.')).toBeInTheDocument()
    expect(patches).toEqual([])
  })

  test('clearing a description says the API cannot remove it', async () => {
    server.use(respond(getTeam, 'get', getGetTeamUrl(settlements.id), 200, described))
    const patches = recordRequests('patch', getUpdateTeamUrl(settlements.id))

    const { findByLabelText, getByRole, findByText, user } = openAs(petraIn('lead'), PATH)
    await user.clear(await findByLabelText('Description'))
    await user.click(getByRole('button', { name: 'Save changes' }))

    expect(await findByText("A description can't be removed yet. Enter a new one instead.")).toBeInTheDocument()
    expect(patches).toEqual([])
  })
})

describe('settings navigation', () => {
  test('/settings opens General and marks it in the sub-navigation', async () => {
    server.use(respond(getTeam, 'get', getGetTeamUrl(settlements.id), 200, described))

    const { findByRole, router } = openAs(petraIn('viewer'), '/teams/settlements/settings')
    const nav = await findByRole('navigation', { name: 'Team settings' })

    await waitFor(() => expect(router.state.location.pathname).toBe(PATH))
    expect(nav.querySelector('[aria-current="page"]')).toHaveTextContent('General')
  })
})
