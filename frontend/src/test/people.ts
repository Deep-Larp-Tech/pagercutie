import type { GlobalRole, MembershipRead, MeRead, TeamRead, TeamRole } from '@/api/generated/model'

/** A team with a fixed id derived from its slug, so tests can compare teams across responses. */
export function team(slug: string, name: string): TeamRead {
  return {
    id: `team-${slug}`,
    slug,
    name,
    description: null,
    created_at: '2026-01-01T00:00:00Z',
  }
}

/** A membership of `team` with `role`. */
export function membership(of: TeamRead, role: TeamRole): MembershipRead {
  return { team: of, role }
}

/** The `GET /me` answer for Petra Dvorak with a global role and memberships fixed by the test. */
export function petra(role: GlobalRole, memberships: MembershipRead[]): MeRead {
  return {
    user: {
      id: '0193a000-0000-7000-8000-000000000002',
      email: 'petra@example.com',
      display_name: 'Petra Dvorak',
      phone: null,
      timezone: 'Europe/Prague',
      role,
      created_at: '2026-01-01T00:00:00Z',
    },
    memberships,
  }
}
