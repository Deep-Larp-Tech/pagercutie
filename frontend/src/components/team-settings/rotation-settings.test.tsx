import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { waitFor, within } from '@testing-library/react'
import type { Rotation } from '@/api/generated/model'
import {
  getGetTeamOnCallUrl,
  getGetTeamRotationUrl,
  getListTeamMembersUrl,
  getSetTeamRotationUrl,
  getTeamOnCall,
  getTeamRotation,
  listTeamMembers,
  setTeamRotation,
} from '@/api/generated/teams/teams'
import { respond } from '@/test/http'
import { server } from '@/test/server'
import { member, openAs, petraIn, recordRequests, settlements, user } from '@/test/teams'

const PATH = '/teams/settlements/settings/rotation'
const lead = petraIn('lead')
const bob = user('bob', 'Bob Novak')
const carol = user('carol', 'Carol Svoboda')
const vera = user('vera', 'Vera Viewer')
const rotation: Rotation = {
  user_ids: [lead.user.id, bob.id, carol.id],
  handoff_day: 'mon',
  handoff_time: '09:00:00',
  timezone: 'Europe/Prague',
}
const rotationUrl = getGetTeamRotationUrl(settlements.id)
const onCallUrl = getGetTeamOnCallUrl(settlements.id)

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-11-21T12:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
})

function withTeam({ saved = rotation, onCall = bob }: { saved?: Rotation | null; onCall?: typeof bob | null } = {}) {
  server.use(
    respond(listTeamMembers, 'get', getListTeamMembersUrl(settlements.id), 200, [
      member(lead.user, 'lead'),
      member(bob, 'member'),
      member(carol, 'member'),
      member(vera, 'viewer'),
    ]),
    respond(getTeamRotation, 'get', rotationUrl, 200, saved),
    respond(getTeamOnCall, 'get', onCallUrl, 200, {
      team_id: settlements.id,
      user: onCall,
      until: onCall === null ? null : '2026-11-23T08:00:00Z',
    }),
  )
}

async function previewRows(findByRole: (role: string, options: { name: string }) => Promise<HTMLElement>, name: string) {
  const list = await findByRole('list', { name })
  return within(list)
    .getAllByRole('listitem')
    .map((item) => item.textContent)
}

describe('GET /teams/{id}/rotation and GET /teams/{id}/on-call', () => {
  test('shows who is on call, the order and the next four shifts from the current on-call person', async () => {
    withTeam()

    const { findByTestId, findByRole } = openAs(lead, PATH)

    expect(await findByTestId('on-call-now')).toHaveTextContent('Bob Novak is on call until Mon 23 Nov, 09:00.')
    const order = await findByRole('list', { name: 'Rotation order' })
    expect(within(order).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      expect.stringContaining('Petra Dvorak'),
      expect.stringContaining('Bob NovakOn call now'),
      expect.stringContaining('Carol Svoboda'),
    ])
    expect(await previewRows(findByRole, 'Next four shifts')).toEqual([
      'Bob NovakNow to Mon 23 Nov, 09:00',
      'Carol SvobodaMon 23 Nov, 09:00 to Mon 30 Nov, 09:00',
      'Petra DvorakMon 30 Nov, 09:00 to Mon 7 Dec, 09:00',
      'Bob NovakMon 7 Dec, 09:00 to Mon 14 Dec, 09:00',
    ])
  })

  test('says so when you are on call', async () => {
    withTeam({ onCall: lead.user })

    const { findByTestId } = openAs(lead, PATH)

    expect(await findByTestId('on-call-now')).toHaveTextContent('You are on call until Mon 23 Nov, 09:00.')
  })

  test('a member sees the order, the handoff and the preview, without controls', async () => {
    withTeam()

    const { findByRole, getByText, queryByRole } = openAs(petraIn('member'), PATH)

    const order = await findByRole('list', { name: 'Rotation order' })
    expect(within(order).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Petra Dvorak',
      'Bob Novak',
      'Carol Svoboda',
    ])
    expect(getByText('Hands over every Monday at 09:00, Europe/Prague time.')).toBeInTheDocument()
    expect(getByText('Only team leads can change this.')).toBeInTheDocument()
    expect(await previewRows(findByRole, 'Next four shifts')).toHaveLength(4)
    expect(queryByRole('button', { name: /Move|Save rotation/ })).not.toBeInTheDocument()
  })

  test('no rotation: no one is on call, and a lead can start one with leads and members only', async () => {
    withTeam({ saved: null, onCall: null })

    const { findByText, findByRole, getByLabelText, user: actor } = openAs(lead, PATH)

    expect(await findByText('No one is on call. The team has no rotation yet.')).toBeInTheDocument()
    expect(await findByText('No one is in the rotation yet.')).toBeInTheDocument()
    await actor.click(getByLabelText('Add to rotation'))
    const options = within(await findByRole('listbox')).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual(['Petra Dvorak', 'Bob Novak', 'Carol Svoboda'])
    await actor.click(options[1])

    expect(await previewRows(findByRole, 'Next four shifts after you save')).toEqual([
      'Bob NovakNow to Mon 23 Nov, 09:00',
      'Bob NovakMon 23 Nov, 09:00 to Mon 30 Nov, 09:00',
      'Bob NovakMon 30 Nov, 09:00 to Mon 7 Dec, 09:00',
      'Bob NovakMon 7 Dec, 09:00 to Mon 14 Dec, 09:00',
    ])
  })

  test('the 501 stubs show the shared fallback', async () => {
    server.use(
      respond(listTeamMembers, 'get', getListTeamMembersUrl(settlements.id), 200, []),
      http.get(rotationUrl, () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
      http.get(onCallUrl, () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )

    const { findAllByRole } = openAs(lead, PATH)

    await waitFor(async () => expect(await findAllByRole('alert')).toHaveLength(2))
    for (const alert of await findAllByRole('alert')) {
      expect(alert).toHaveTextContent("This feature isn't available yet.")
    }
  })

  test('an undocumented 403 shows the shared fallback', async () => {
    withTeam()
    server.use(http.get(rotationUrl, () => HttpResponse.json({ detail: 'x' }, { status: 403 })))

    const { findByRole } = openAs(lead, PATH)

    expect(await findByRole('alert')).toHaveTextContent('Something went wrong on the server (HTTP 403).')
  })
})

describe('PUT /teams/{id}/rotation', () => {
  test('moving someone up previews the restarted rotation; 200 saves the new order', async () => {
    withTeam()
    const putUrl = getSetTeamRotationUrl(settlements.id)
    server.use(respond(setTeamRotation, 'put', putUrl, 200, { ...rotation, user_ids: [lead.user.id, carol.id, bob.id] }))
    const puts = recordRequests('put', putUrl)

    const { findByRole, getByRole, findByText, user: actor } = openAs(lead, PATH)
    await actor.click(await findByRole('button', { name: 'Move Carol Svoboda up' }))

    expect(await previewRows(findByRole, 'Next four shifts after you save')).toEqual([
      'Petra DvorakNow to Mon 23 Nov, 09:00',
      'Carol SvobodaMon 23 Nov, 09:00 to Mon 30 Nov, 09:00',
      'Bob NovakMon 30 Nov, 09:00 to Mon 7 Dec, 09:00',
      'Petra DvorakMon 7 Dec, 09:00 to Mon 14 Dec, 09:00',
    ])
    await actor.click(getByRole('button', { name: 'Save rotation' }))

    expect(await findByText('Rotation saved')).toBeInTheDocument()
    await waitFor(() =>
      expect(puts.map(({ body }) => body)).toEqual([
        {
          user_ids: [lead.user.id, carol.id, bob.id],
          handoff_day: 'mon',
          handoff_time: '09:00',
          timezone: 'Europe/Prague',
        },
      ]),
    )
  })

  test('an invalid HH:MM is caught before sending', async () => {
    withTeam()
    const puts = recordRequests('put', getSetTeamRotationUrl(settlements.id))

    const { findByLabelText, getByRole, findByText, user: actor } = openAs(lead, PATH)
    const time = await findByLabelText('Handoff time')
    await actor.clear(time)
    await actor.type(time, '9am')
    await actor.click(getByRole('button', { name: 'Save rotation' }))

    expect(await findByText('Enter a time as HH:MM, e.g. 09:00.')).toBeInTheDocument()
    expect(puts).toEqual([])
  })

  test('422 for the handoff time shows the message under that field', async () => {
    withTeam()
    server.use(
      respond(setTeamRotation, 'put', getSetTeamRotationUrl(settlements.id), 422, {
        detail: [{ loc: ['body', 'handoff_time'], msg: 'Input should be in a valid time format', type: 'time_parsing' }],
      }),
    )

    const { findByLabelText, getByRole, findByText, user: actor } = openAs(lead, PATH)
    const time = await findByLabelText('Handoff time')
    await actor.clear(time)
    await actor.type(time, '10:30')
    await actor.click(getByRole('button', { name: 'Save rotation' }))

    expect(await findByText('Input should be in a valid time format')).toHaveAttribute('data-slot', 'field-error')
  })

  test('403 says only leads can change it', async () => {
    withTeam()
    server.use(respond(setTeamRotation, 'put', getSetTeamRotationUrl(settlements.id), 403, { detail: 'Forbidden' }))

    const { findByRole, getByRole, user: actor } = openAs(lead, PATH)
    await actor.click(await findByRole('button', { name: 'Move Bob Novak down' }))
    await actor.click(getByRole('button', { name: 'Save rotation' }))

    expect(await findByRole('alert')).toHaveTextContent('Only team leads can change this.')
  })

  test('the 501 stub shows the shared fallback', async () => {
    withTeam()
    server.use(
      http.put(getSetTeamRotationUrl(settlements.id), () => HttpResponse.json({ detail: 'x' }, { status: 501 })),
    )

    const { findByRole, getByRole, user: actor } = openAs(lead, PATH)
    await actor.click(await findByRole('button', { name: 'Remove Carol Svoboda from the rotation' }))
    await actor.click(getByRole('button', { name: 'Save rotation' }))

    expect(await findByRole('alert')).toHaveTextContent("This feature isn't available yet.")
  })
})
