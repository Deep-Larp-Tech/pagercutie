import { expect, test } from 'vitest'
import type { MemberRead, TeamRole } from '@/api/generated/model'
import { isLastLead } from './roles'

function member(id: string, role: TeamRole): MemberRead {
  return {
    user: {
      id,
      email: `${id}@example.com`,
      display_name: id,
      phone: null,
      timezone: 'UTC',
      role: 'user',
      created_at: '2026-01-01T00:00:00Z',
    },
    role,
  }
}

test('the only lead is the last lead; members and one of two leads are not', () => {
  const ana = member('ana', 'lead')
  const bob = member('bob', 'member')
  const cid = member('cid', 'lead')

  expect(isLastLead(ana, [ana, bob])).toBe(true)
  expect(isLastLead(bob, [ana, bob])).toBe(false)
  expect(isLastLead(ana, [ana, bob, cid])).toBe(false)
})
