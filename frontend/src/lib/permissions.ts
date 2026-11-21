import type { AlertRead, MeRead, TeamRole } from '@/api/generated/model'

/** Teams whose roles decide who works an alert: its owning team (null for a personal rule) and escalation targets. */
export type AlertTeams = Pick<AlertRead, 'team_id' | 'escalated_team_ids'>

/**
 * One permission check: an action from DOMAIN.md §4 followed by the scope it needs. A team action without a team
 * id, or an alert action without the alert, is a type error.
 */
export type Check =
  /** See a team, its alerts, rules, runbooks, sources and schemas: any role in the team. */
  | [action: 'team.read', teamId: string]
  /** Create, edit or delete the team's rules, runbooks, sources and event schemas: member or lead. */
  | [action: 'team.config.edit', teamId: string]
  /** Add or remove members, change roles, edit the rotation and team preferences: lead. */
  | [action: 'team.members.manage', teamId: string]
  /** Read the audit entries that belong to the team: any role in the team. */
  | [action: 'audit.read', teamId: string]
  /** Read any event schema, of any team, so rules can use other teams' schemas: everyone. */
  | [action: 'event-schema.read']
  /** Acknowledge or resolve, tick a manual step, answer a guard question: member or lead of an alert team. */
  | [action: 'alert.respond', alert: AlertTeams]
  /** Approve or reject a risky runbook step (`RUN-4`): lead of an alert team. */
  | [action: 'step.approve', alert: AlertTeams]
  /** Create, edit or delete a personal rule: the owning user. */
  | [action: 'personal-rule.edit', ownerUserId: string]
  /** Edit a user's profile and channel preferences: the user themselves. */
  | [action: 'profile.edit', userId: string]
  /** Create users and teams, change global roles: admin only. */
  | [action: 'users-and-teams.manage']

/** Every action `can` answers. */
export type Action = Check[0]

function teamRole(me: MeRead, teamId: string): TeamRole | undefined {
  return me.memberships.find((membership) => membership.team.id === teamId)?.role
}

function hasRoleIn(me: MeRead, teamIds: readonly string[], roles: readonly TeamRole[]): boolean {
  return teamIds.some((teamId) => {
    const role = teamRole(me, teamId)
    return role !== undefined && roles.includes(role)
  })
}

function alertTeamIds({ team_id, escalated_team_ids }: AlertTeams): string[] {
  return team_id === null ? escalated_team_ids : [team_id, ...escalated_team_ids]
}

/**
 * Whether `me` may perform an action (DOMAIN.md §4); hides controls only, the API stays the authority.
 *
 * An admin may do everything except edit another user's personal rule. For an alert from a personal rule
 * (`team_id: null`) that was never escalated, only an admin gets `true`: `AlertRead` does not say which user owns the
 * rule, so the caller decides for the owner.
 */
export function can(me: MeRead, ...check: Check): boolean {
  const [action, scope] = check
  if (action === 'personal-rule.edit') return scope === me.user.id
  if (me.user.role === 'admin') return true
  switch (action) {
    case 'team.read':
    case 'audit.read':
      return teamRole(me, scope) !== undefined
    case 'team.config.edit':
      return hasRoleIn(me, [scope], ['lead', 'member'])
    case 'team.members.manage':
      return hasRoleIn(me, [scope], ['lead'])
    case 'event-schema.read':
      return true
    case 'alert.respond':
      return hasRoleIn(me, alertTeamIds(scope), ['lead', 'member'])
    case 'step.approve':
      return hasRoleIn(me, alertTeamIds(scope), ['lead'])
    case 'profile.edit':
      return scope === me.user.id
    case 'users-and-teams.manage':
      return false
    default:
      return action satisfies never
  }
}
