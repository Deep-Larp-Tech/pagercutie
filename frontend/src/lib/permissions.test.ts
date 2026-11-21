import { describe, expect, expectTypeOf, test } from 'vitest'
import type { GlobalRole, MeRead, TeamRole } from '@/api/generated/model'
import { can, type AlertTeams, type Check } from './permissions'

const TEAM = 'team-settlement'
const OTHER_TEAM = 'team-payments'

function team(id: string) {
  return { id, slug: id, name: id, description: null, created_at: '2026-01-01T00:00:00Z' }
}

function person(id: string, role: GlobalRole, memberships: [teamId: string, role: TeamRole][]): MeRead {
  return {
    user: {
      id,
      email: `${id}@example.com`,
      display_name: id,
      phone: null,
      timezone: 'Europe/Prague',
      role,
      created_at: '2026-01-01T00:00:00Z',
    },
    memberships: memberships.map(([teamId, teamRole]) => ({ team: team(teamId), role: teamRole })),
  }
}

/** One persona per row column of DOMAIN.md §4; `nonMember` belongs to another team only. */
const personas = {
  admin: person('admin', 'admin', []),
  lead: person('lead', 'user', [[TEAM, 'lead']]),
  member: person('member', 'user', [[TEAM, 'member']]),
  viewer: person('viewer', 'user', [[TEAM, 'viewer']]),
  nonMember: person('non-member', 'user', [[OTHER_TEAM, 'lead']]),
} as const satisfies Record<string, MeRead>

type Persona = keyof typeof personas
const personaNames = ['admin', 'lead', 'member', 'viewer', 'nonMember'] as const satisfies readonly Persona[]
type Expected = Record<Persona, boolean>

const ownAlert: AlertTeams = { team_id: TEAM, escalated_team_ids: [] }
/** Owned by another team and escalated to `TEAM`. */
const escalatedAlert: AlertTeams = { team_id: 'team-ledger', escalated_team_ids: [TEAM] }
/** From someone's personal rule, never escalated. */
const personalAlert: AlertTeams = { team_id: null, escalated_team_ids: [] }

const rows: [label: string, check: (me: MeRead) => Check, expected: Expected][] = [
  [
    'see the team, its alerts, rules, runbooks, sources and schemas',
    () => ['team.read', TEAM],
    { admin: true, lead: true, member: true, viewer: true, nonMember: false },
  ],
  [
    "read any team's event schema",
    () => ['event-schema.read'],
    { admin: true, lead: true, member: true, viewer: true, nonMember: true },
  ],
  [
    "respond to an alert of the user's team",
    () => ['alert.respond', ownAlert],
    { admin: true, lead: true, member: true, viewer: false, nonMember: false },
  ],
  [
    "respond to an alert escalated to the user's team",
    () => ['alert.respond', escalatedAlert],
    { admin: true, lead: true, member: true, viewer: false, nonMember: false },
  ],
  [
    'respond to an alert from a personal rule',
    () => ['alert.respond', personalAlert],
    { admin: true, lead: false, member: false, viewer: false, nonMember: false },
  ],
  [
    "approve a risky step on an alert of the user's team",
    () => ['step.approve', ownAlert],
    { admin: true, lead: true, member: false, viewer: false, nonMember: false },
  ],
  [
    "approve a risky step on an alert escalated to the user's team",
    () => ['step.approve', escalatedAlert],
    { admin: true, lead: true, member: false, viewer: false, nonMember: false },
  ],
  [
    'create, edit or delete team rules, runbooks, sources and event schemas',
    () => ['team.config.edit', TEAM],
    { admin: true, lead: true, member: true, viewer: false, nonMember: false },
  ],
  [
    'manage members, roles, rotation and team preferences',
    () => ['team.members.manage', TEAM],
    { admin: true, lead: true, member: false, viewer: false, nonMember: false },
  ],
  [
    'edit their own personal rule',
    (me) => ['personal-rule.edit', me.user.id],
    { admin: true, lead: true, member: true, viewer: true, nonMember: true },
  ],
  [
    "edit someone else's personal rule",
    () => ['personal-rule.edit', 'someone-else'],
    { admin: false, lead: false, member: false, viewer: false, nonMember: false },
  ],
  [
    'edit their own profile and preferences',
    (me) => ['profile.edit', me.user.id],
    { admin: true, lead: true, member: true, viewer: true, nonMember: true },
  ],
  [
    "edit someone else's profile and preferences",
    () => ['profile.edit', 'someone-else'],
    { admin: true, lead: false, member: false, viewer: false, nonMember: false },
  ],
  [
    'create users and teams, change global roles',
    () => ['users-and-teams.manage'],
    { admin: true, lead: false, member: false, viewer: false, nonMember: false },
  ],
  [
    "read the team's audit log",
    () => ['audit.read', TEAM],
    { admin: true, lead: true, member: true, viewer: true, nonMember: false },
  ],
]

describe('can', () => {
  describe.each(rows)('%s', (_label, check, expected) => {
    test.each(personaNames)('%s', (persona) => {
      const me = personas[persona]
      expect(can(me, ...check(me))).toBe(expected[persona])
    })
  })

  test('a scoped action needs its scope', () => {
    expectTypeOf<['team.read']>().not.toExtend<Check>()
    expectTypeOf<['alert.respond', string]>().not.toExtend<Check>()
    expectTypeOf<['team.read', string]>().toExtend<Check>()
  })
})
