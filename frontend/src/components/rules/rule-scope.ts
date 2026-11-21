import { getRouteApi, useNavigate } from '@tanstack/react-router'
import type { ListRulesParams, Owner, Recipient, TeamRead } from '@/api/generated/model'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'

/** Whose rules a screen shows: a team's (`/teams/$team/rules`) or the signed-in user's personal rules (`/me/rules`). */
export type RuleScope =
  | {
      kind: 'team'
      team: TeamRead
      /** Members and leads edit team rules (`team.config.edit`). */
      canEdit: boolean
    }
  | {
      kind: 'personal'
      userId: string
      /** Only the owner edits a personal rule, admins included (DOMAIN.md §4). */
      canEdit: boolean
    }

const teamRoute = getRouteApi('/_app/teams/$team')

/** The scope of a screen under `/teams/$team/rules`. */
export function useTeamRuleScope(): RuleScope {
  const me = useMe()
  const team = teamRoute.useRouteContext({ select: (context) => context.team })
  return { kind: 'team', team, canEdit: can(me, 'team.config.edit', team.id) }
}

/** The scope of a screen under `/me/rules`. */
export function usePersonalRuleScope(): RuleScope {
  const me = useMe()
  return { kind: 'personal', userId: me.user.id, canEdit: can(me, 'personal-rule.edit', me.user.id) }
}

/** `owner` of a rule created in the scope. */
export function scopeOwner(scope: RuleScope): Owner {
  return scope.kind === 'team' ? { type: 'team', team_id: scope.team.id } : { type: 'user', user_id: scope.userId }
}

/** `GET /rules` filter for the scope. */
export function scopeListParams(scope: RuleScope): ListRulesParams {
  return scope.kind === 'team' ? { team_id: scope.team.id } : { user_id: scope.userId }
}

/** Whether a rule with `owner` belongs on the scope's screens; any other rule shows the 404 page. */
export function ownedByScope(scope: RuleScope, owner: Owner): boolean {
  if (scope.kind === 'team') return owner.type === 'team' && owner.team_id === scope.team.id
  return owner.type === 'user' && owner.user_id === scope.userId
}

/**
 * Recipients of a new rule: the team's on-call person, or the owner for a personal rule, which notifies only its user
 * (ADR-0026).
 */
export function defaultRecipients(scope: RuleScope): Recipient[] {
  return scope.kind === 'team' ? [{ type: 'on_call', team_id: scope.team.id }] : [{ type: 'user', user_id: scope.userId }]
}

/** Navigates to the scope's rule list. */
export function useToRuleList(scope: RuleScope): () => Promise<void> {
  const navigate = useNavigate()
  return () =>
    scope.kind === 'team'
      ? navigate({ to: '/teams/$team/rules', params: { team: scope.team.slug } })
      : navigate({ to: '/me/rules' })
}
