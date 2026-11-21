import { getRouteApi } from '@tanstack/react-router'
import type { MeRead, TeamRead } from '@/api/generated/model'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'

const teamRoute = getRouteApi('/_app/teams/$team')

/** What every team settings page needs: the signed-in user, the team from the URL, and whether they may edit. */
export interface TeamSettings {
  me: MeRead
  team: TeamRead
  /** Leads and admins edit members, rotation, team preferences and the team's name (`team.members.manage`). */
  canEdit: boolean
}

/** The team settings scope, for pages under `/teams/$team/settings`. */
export function useTeamSettings(): TeamSettings {
  const me = useMe()
  const team = teamRoute.useRouteContext({ select: (context) => context.team })
  return { me, team, canEdit: can(me, 'team.members.manage', team.id) }
}
