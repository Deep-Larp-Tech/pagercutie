import { useQuery } from '@tanstack/react-query'
import { useParams } from '@tanstack/react-router'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'
import {
  adminTeamsQueryOptions,
  findTeam,
  listedTeams,
  readLastTeam,
  teamList,
  visibleTeams,
  type TeamList,
  type VisibleTeam,
} from '@/lib/teams'

/** Teams the signed-in user can open, how the admin's `GET /teams` went, and the team the shell points at. */
export interface VisibleTeams {
  teams: VisibleTeam[]
  list: TeamList
  /** The team in the URL when it is one of `teams`, else `undefined`. */
  inUrl: VisibleTeam | undefined
  /**
   * Team the sidebar's team links point at: `inUrl`, else the last team opened in this browser, else the first team.
   * `undefined` when the user can open none.
   */
  current: VisibleTeam | undefined
}

/**
 * Memberships for everyone; admins also get every team from `GET /teams`. Non-admins send no request. While the list
 * is loading or unavailable (the `501` stub), admins see their memberships.
 *
 * The team comes from the `$team` param, not the team route's context: on the 404 page for an unknown slug the
 * route's match exists but its `beforeLoad` never returned a team.
 */
export function useVisibleTeams(): VisibleTeams {
  const me = useMe()
  const isAdmin = can(me, 'users-and-teams.manage')
  const { data, isPending } = useQuery({ ...adminTeamsQueryOptions, enabled: isAdmin })
  const slug = useParams({ strict: false, select: (params) => params.team })
  let list: TeamList = { kind: 'unavailable' }
  if (isAdmin) list = isPending ? { kind: 'loading' } : teamList(data)
  const teams = visibleTeams(me, listedTeams(list))
  const inUrl = slug === undefined ? undefined : findTeam(teams, slug)
  const last = readLastTeam()
  const current = inUrl ?? (last === null ? undefined : findTeam(teams, last)) ?? teams[0]
  return { teams, list, inUrl, current }
}
