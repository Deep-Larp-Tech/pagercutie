import type { MemberRead, TeamRole } from '@/api/generated/model'

/** User-facing team role name. */
export const roleLabel = {
  lead: 'Lead',
  member: 'Member',
  viewer: 'Viewer',
} as const satisfies Record<TeamRole, string>

/** Team roles from most to least rights. */
export const TEAM_ROLES = ['lead', 'member', 'viewer'] as const satisfies readonly TeamRole[]

/** Whether `member` is the team's only lead, who must stay a lead (client check; the API is the authority). */
export function isLastLead(member: MemberRead, members: readonly MemberRead[]): boolean {
  return member.role === 'lead' && members.filter(({ role }) => role === 'lead').length === 1
}
