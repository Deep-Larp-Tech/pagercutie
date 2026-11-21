import { useEffect } from 'react'
import { createFileRoute, notFound, Outlet, redirect } from '@tanstack/react-router'
import { NotFoundPage } from '@/components/shell/not-found-page'
import { can } from '@/lib/permissions'
import { adminTeamsQueryOptions, findTeam, listedTeams, rememberTeam, teamList, visibleTeams } from '@/lib/teams'

/**
 * Team scope (ADR-0047): resolves the `$team` slug to a team the user can open and puts it, with the user's role, in
 * the route context. Memberships come first and need no request; an admin's other teams come from `GET /teams`. A
 * slug the user cannot open shows the 404 page, so a team's existence is not revealed.
 */
export const Route = createFileRoute('/_app/teams/$team')({
  beforeLoad: async ({ context: { me, queryClient }, params, location }) => {
    const membership = findTeam(visibleTeams(me, null), params.team)
    if (membership !== undefined) return { team: membership.team, teamRole: membership.role }
    if (!can(me, 'users-and-teams.manage')) throw notFound()

    const response = await queryClient.fetchQuery(adminTeamsQueryOptions)
    if (response.status === 401) throw redirect({ to: '/login', search: { redirect: location.href } })
    const listed = findTeam(visibleTeams(me, listedTeams(teamList(response))), params.team)
    if (listed === undefined) throw notFound()
    return { team: listed.team, teamRole: listed.role }
  },
  component: TeamLayout,
  notFoundComponent: NotFoundPage,
})

function TeamLayout() {
  const slug = Route.useRouteContext({ select: (context) => context.team.slug })
  useEffect(() => rememberTeam(slug), [slug])
  return <Outlet />
}
