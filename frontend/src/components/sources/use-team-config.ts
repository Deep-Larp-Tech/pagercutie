import { getRouteApi } from '@tanstack/react-router'
import type { MeRead, TeamRead } from '@/api/generated/model'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'

const teamRoute = getRouteApi('/_app/teams/$team')

/** What a team configuration page (sources, event schemas) needs: the user, the team from the URL, edit rights. */
export interface TeamConfig {
  me: MeRead
  team: TeamRead
  /** Members, leads and admins create, edit and delete sources and event schemas (`team.config.edit`). */
  canEdit: boolean
}

/** The team configuration scope, for pages under `/teams/$team/sources` and `/teams/$team/schemas`. */
export function useTeamConfig(): TeamConfig {
  const me = useMe()
  const team = teamRoute.useRouteContext({ select: (context) => context.team })
  return { me, team, canEdit: can(me, 'team.config.edit', team.id) }
}

/** Shown once at the top of a team configuration page to a viewer. */
export const READ_ONLY_NOTICE = 'Only members and leads can change this.'
