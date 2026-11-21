import { describe, expect, test } from 'vitest'
import { membership, petra, team } from '@/test/people'
import { teamList, visibleTeams } from './teams'

const settlements = team('settlements', 'Settlements')
const payments = team('payments', 'Payments')
const billing = team('billing', 'Billing')

describe('visibleTeams', () => {
  test('lists memberships first, then the other listed teams by name', () => {
    const me = petra('admin', [membership(settlements, 'lead')])

    const teams = visibleTeams(me, [payments, settlements, billing])

    expect(teams).toEqual([
      { team: settlements, role: 'lead' },
      { team: billing, role: null },
      { team: payments, role: null },
    ])
  })

  test('without a list it returns the memberships', () => {
    const me = petra('user', [membership(payments, 'viewer')])

    expect(visibleTeams(me, null)).toEqual([{ team: payments, role: 'viewer' }])
  })
})

describe('teamList', () => {
  test('200 lists the teams, 401 is unavailable, 422 fails with a message', () => {
    const headers = new Headers()
    expect(teamList({ status: 200, data: [billing], headers })).toEqual({ kind: 'listed', teams: [billing] })
    expect(teamList({ status: 401, data: { detail: 'x' }, headers })).toEqual({ kind: 'unavailable' })
    expect(teamList({ status: 422, data: { detail: [] }, headers }).kind).toBe('failed')
    expect(teamList(undefined)).toEqual({ kind: 'unavailable' })
  })
})
