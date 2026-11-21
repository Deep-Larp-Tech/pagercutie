import { http, HttpResponse } from 'msw'
import { describe, expect, test } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import type { MemberRead } from '@/api/generated/model'
import {
  getListTeamMembersUrl,
  getRemoveTeamMemberUrl,
  getSetTeamMemberUrl,
  listTeamMembers,
  removeTeamMember,
  setTeamMember,
} from '@/api/generated/teams/teams'
import { getListUsersUrl, listUsers } from '@/api/generated/users/users'
import { respond } from '@/test/http'
import { server } from '@/test/server'
import { member, openAs, petraIn, recordRequests, settlements, user } from '@/test/teams'

const PATH = '/teams/settlements/settings/members'
const lead = petraIn('lead')
const petra = member(lead.user, 'lead')
const bob = member(user('bob', 'Bob Novak'), 'member')
const carol = user('carol', 'Carol Svoboda')
const membersUrl = getListTeamMembersUrl(settlements.id)

function withMembers(members: MemberRead[]) {
  server.use(respond(listTeamMembers, 'get', membersUrl, 200, members))
}

describe('GET /teams/{id}/members', () => {
  test('lists name, email and role; a lead gets role selects and Remove', async () => {
    withMembers([petra, bob])

    const { findByRole, getByRole } = openAs(lead, PATH)
    const table = await findByRole('table')

    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining('Petra Dvorakpetra@example.com'),
      expect.stringContaining('Bob Novakbob@example.com'),
    ])
    expect(getByRole('combobox', { name: 'Role of Bob Novak' })).toHaveTextContent('Member')
    expect(getByRole('button', { name: 'Remove Bob Novak' })).toBeEnabled()
  })

  test('a member sees the list read-only and sends no GET /users', async () => {
    withMembers([petra, bob])

    const { findByRole, getByText, queryByRole, queryByLabelText } = openAs(petraIn('member'), PATH)
    const table = await findByRole('table')

    expect(within(table).getAllByRole('row')[2]).toHaveTextContent('Bob Novakbob@example.comMember')
    expect(getByText('Only team leads can change this.')).toBeInTheDocument()
    expect(queryByRole('button', { name: /Remove/ })).not.toBeInTheDocument()
    expect(queryByLabelText('Add a person')).not.toBeInTheDocument()
  })

  test('the 501 stub shows the shared fallback', async () => {
    server.use(http.get(membersUrl, () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole } = openAs(lead, PATH)

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })

  test('an undocumented 403 shows the shared fallback', async () => {
    server.use(http.get(membersUrl, () => HttpResponse.json({ detail: 'x' }, { status: 403 })))

    const { findByRole } = openAs(lead, PATH)

    expect(await findByRole('alert')).toHaveTextContent('Something went wrong on the server (HTTP 403).')
  })

  test('the last lead cannot be demoted or removed', async () => {
    withMembers([petra, bob])

    const { findByRole, getByRole, getByText } = openAs(lead, PATH)

    const role = await findByRole('combobox', { name: 'Role of Petra Dvorak' })
    expect(role).toHaveAttribute('data-disabled')
    expect(getByRole('button', { name: 'Remove Petra Dvorak' })).toBeDisabled()
    expect(role).toHaveAccessibleDescription('Each team needs a lead. Make someone else a lead first.')
    expect(getByText('Each team needs a lead. Make someone else a lead first.')).toBeInTheDocument()
  })

  test('with two leads either can be demoted', async () => {
    withMembers([petra, member(bob.user, 'lead')])

    const { findByRole, getByRole, queryByText } = openAs(lead, PATH)

    expect(await findByRole('combobox', { name: 'Role of Petra Dvorak' })).not.toHaveAttribute('data-disabled')
    expect(getByRole('button', { name: 'Remove Bob Novak' })).toBeEnabled()
    expect(queryByText('Each team needs a lead. Make someone else a lead first.')).not.toBeInTheDocument()
  })
})

describe('PUT /teams/{id}/members/{user_id} (change role)', () => {
  async function pickRole(name: string, role: string) {
    const rendered = openAs(lead, PATH)
    await rendered.user.click(await rendered.findByRole('combobox', { name: `Role of ${name}` }))
    await rendered.user.click(await rendered.findByRole('option', { name: role }))
    return rendered
  }

  test('200 sends the role, reloads the list and says so', async () => {
    withMembers([petra, bob])
    const url = getSetTeamMemberUrl(settlements.id, bob.user.id)
    server.use(respond(setTeamMember, 'put', url, 200, member(bob.user, 'viewer')))
    const puts = recordRequests('put', url)
    const lists = recordRequests('get', membersUrl)

    const { findByText } = await pickRole('Bob Novak', 'Viewer')

    expect(await findByText('Bob Novak is now a viewer')).toBeInTheDocument()
    await waitFor(() => expect(puts.map(({ body }) => body)).toEqual([{ role: 'viewer' }]))
    expect(lists.length).toBeGreaterThan(1)
  })

  test('403 says only leads can change it', async () => {
    withMembers([petra, bob])
    server.use(
      respond(setTeamMember, 'put', getSetTeamMemberUrl(settlements.id, bob.user.id), 403, { detail: 'Forbidden' }),
    )

    const { findByRole } = await pickRole('Bob Novak', 'Lead')

    expect(await findByRole('alert')).toHaveTextContent('Only team leads can change this.')
  })

  test('422 shows the API message', async () => {
    withMembers([petra, bob])
    server.use(
      respond(setTeamMember, 'put', getSetTeamMemberUrl(settlements.id, bob.user.id), 422, {
        detail: [{ loc: ['body', 'role'], msg: "Input should be 'lead', 'member' or 'viewer'", type: 'enum' }],
      }),
    )

    const { findByRole } = await pickRole('Bob Novak', 'Lead')

    expect(await findByRole('alert')).toHaveTextContent("Input should be 'lead', 'member' or 'viewer'")
  })

  test('the 501 stub shows the shared fallback', async () => {
    withMembers([petra, bob])
    server.use(
      http.put(getSetTeamMemberUrl(settlements.id, bob.user.id), () =>
        HttpResponse.json({ detail: 'x' }, { status: 501 }),
      ),
    )

    const { findByRole } = await pickRole('Bob Novak', 'Lead')

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('DELETE /teams/{id}/members/{user_id}', () => {
  async function confirmRemove() {
    const rendered = openAs(lead, PATH)
    await rendered.user.click(await rendered.findByRole('button', { name: 'Remove Bob Novak' }))
    const dialog = await rendered.findByRole('dialog', { name: 'Remove Bob Novak from Settlements?' })
    await rendered.user.click(within(dialog).getByRole('button', { name: 'Remove member' }))
    return { ...rendered, dialog }
  }

  test('204 after confirming removes the member and says so', async () => {
    withMembers([petra, bob])
    const url = getRemoveTeamMemberUrl(settlements.id, bob.user.id)
    server.use(respond(removeTeamMember, 'delete', url, 204, undefined))
    const deletes = recordRequests('delete', url)

    const { findByText, queryByRole } = await confirmRemove()

    expect(await findByText('Bob Novak removed from Settlements')).toBeInTheDocument()
    expect(deletes).toHaveLength(1)
    await waitFor(() => expect(queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('Cancel closes the dialog without a request', async () => {
    withMembers([petra, bob])
    const deletes = recordRequests('delete', getRemoveTeamMemberUrl(settlements.id, bob.user.id))

    const { findByRole, user: actor, queryByRole } = openAs(lead, PATH)
    await actor.click(await findByRole('button', { name: 'Remove Bob Novak' }))
    await actor.click(await findByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(queryByRole('dialog')).not.toBeInTheDocument())
    expect(deletes).toEqual([])
  })

  test('409 shows the reason in the dialog', async () => {
    withMembers([petra, bob])
    server.use(
      respond(removeTeamMember, 'delete', getRemoveTeamMemberUrl(settlements.id, bob.user.id), 409, {
        detail: 'Bob Novak is in the rotation.',
      }),
    )

    const { dialog } = await confirmRemove()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      "Couldn't remove Bob Novak. Bob Novak is in the rotation.",
    )
  })

  test('403 says only leads can change it', async () => {
    withMembers([petra, bob])
    server.use(
      respond(removeTeamMember, 'delete', getRemoveTeamMemberUrl(settlements.id, bob.user.id), 403, {
        detail: 'Forbidden',
      }),
    )

    const { dialog } = await confirmRemove()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Only team leads can change this.')
  })

  test('the 501 stub shows the shared fallback', async () => {
    withMembers([petra, bob])
    server.use(
      http.delete(getRemoveTeamMemberUrl(settlements.id, bob.user.id), () =>
        HttpResponse.json({ detail: 'x' }, { status: 501 }),
      ),
    )

    const { dialog } = await confirmRemove()

    expect(await within(dialog).findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})

describe('GET /users and PUT /teams/{id}/members/{user_id} (add a member)', () => {
  test('the combobox offers people outside the team; Add member sends the picked role', async () => {
    withMembers([petra, bob])
    const url = getSetTeamMemberUrl(settlements.id, carol.id)
    server.use(
      respond(listUsers, 'get', getListUsersUrl(), 200, [lead.user, bob.user, carol]),
      respond(setTeamMember, 'put', url, 200, member(carol, 'viewer')),
    )
    const puts = recordRequests('put', url)

    const { findByRole, findByText, getByRole, getByLabelText, user: actor } = openAs(lead, PATH)
    await actor.type(await findByRole('combobox', { name: 'Add a person' }), 'car')
    const listbox = await findByRole('listbox')
    expect(within(listbox).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Carol Svobodacarol@example.com',
    ])
    await actor.keyboard('{ArrowDown}{Enter}')
    await actor.click(getByLabelText('Role'))
    await actor.click(await findByRole('option', { name: 'Viewer' }))
    await actor.click(getByRole('button', { name: 'Add member' }))

    expect(await findByText('Carol Svoboda added as a viewer')).toBeInTheDocument()
    await waitFor(() => expect(puts.map(({ body }) => body)).toEqual([{ role: 'viewer' }]))
  })

  test('the 501 stub of GET /users shows the fallback inside the list', async () => {
    withMembers([petra, bob])
    server.use(http.get(getListUsersUrl(), () => HttpResponse.json({ detail: 'x' }, { status: 501 })))

    const { findByRole, findByText, user: actor } = openAs(lead, PATH)
    await actor.type(await findByRole('combobox', { name: 'Add a person' }), 'a')

    expect(await findByText("This feature isn't available yet.")).toBeInTheDocument()
  })

  test('Add member without a person asks for one', async () => {
    withMembers([petra, bob])

    const { findByRole } = openAs(lead, PATH)
    const add = await findByRole('button', { name: 'Add member' })
    add.click()

    expect(await findByRole('alert')).toHaveTextContent('Pick a person to add.')
  })

  test('the 501 stub of PUT shows the shared fallback', async () => {
    withMembers([petra, bob])
    server.use(
      respond(listUsers, 'get', getListUsersUrl(), 200, [carol]),
      http.put(getSetTeamMemberUrl(settlements.id, carol.id), () =>
        HttpResponse.json({ detail: 'x' }, { status: 501 }),
      ),
    )

    const { findByRole, getByRole, user: actor } = openAs(lead, PATH)
    await actor.type(await findByRole('combobox', { name: 'Add a person' }), 'Carol')
    await actor.click(await findByRole('option', { name: /Carol Svoboda/ }))
    await actor.click(getByRole('button', { name: 'Add member' }))

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})
