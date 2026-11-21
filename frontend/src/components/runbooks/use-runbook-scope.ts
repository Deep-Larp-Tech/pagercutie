import { getRouteApi } from '@tanstack/react-router'
import type { TeamRead } from '@/api/generated/model'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'

const teamRoute = getRouteApi('/_app/teams/$team')

/** What every runbook page needs: the team from the URL and whether the user may change its runbooks. */
export interface RunbookScope {
  team: TeamRead
  /** Members, leads and admins create, edit and delete runbooks (`team.config.edit`). */
  canEdit: boolean
}

/** The runbook scope, for pages under `/teams/$team/runbooks`. */
export function useRunbookScope(): RunbookScope {
  const me = useMe()
  const team = teamRoute.useRouteContext({ select: (context) => context.team })
  return { team, canEdit: can(me, 'team.config.edit', team.id) }
}
