import { getListTeamsQueryOptions, type listTeamsResponse } from '@/api/generated/teams/teams'
import type { MeRead, TeamRead, TeamRole } from '@/api/generated/model'

/** `localStorage` key holding the slug of the team the user opened last (ADR-0047; convenience only). */
const LAST_TEAM_KEY = 'last-team'

/** Largest page `GET /teams` allows; the response carries no total, so admins see at most this many teams. */
const TEAMS_PAGE_LIMIT = 100

/** `GET /teams` for admins: the team switcher and the team layout share this cache entry. */
export const adminTeamsQueryOptions = getListTeamsQueryOptions({ limit: TEAMS_PAGE_LIMIT })

/** A team the user can open, with their role in it. */
export interface VisibleTeam {
  team: TeamRead
  /** The user's team role; `null` for an admin who is not a member of the team. */
  role: TeamRole | null
}

/** What a `GET /teams` answer gives the team switcher and the team layout. */
export type TeamList =
  /** `200`: every team. */
  | { kind: 'listed'; teams: TeamRead[] }
  /** A documented error the user should know about; memberships stand in for the list. */
  | { kind: 'failed'; message: string }
  /** The request is still in flight. */
  | { kind: 'loading' }
  /** No list and nothing to say: no answer (a network error), a `401` (the sign-in redirect is under way) or an undocumented status such as the `501` stub. */
  | { kind: 'unavailable' }

/** Reads a `GET /teams` answer; only `200` lists teams, and the caller falls back to memberships otherwise. */
export function teamList(response: listTeamsResponse | undefined): TeamList {
  if (response === undefined) return { kind: 'unavailable' }
  switch (response.status) {
    case 200:
      return { kind: 'listed', teams: response.data }
    case 401:
      return { kind: 'unavailable' }
    case 422:
      return { kind: 'failed', message: "Couldn't load every team. Showing your teams only." }
    default:
      response satisfies never
      return { kind: 'unavailable' }
  }
}

/** The teams in a `TeamList`, or `null` when it lists none. */
export function listedTeams(list: TeamList): TeamRead[] | null {
  return list.kind === 'listed' ? list.teams : null
}

/**
 * Teams the user can open, memberships first in their order, then the other listed teams by name. `listed` is the
 * admin's `GET /teams` result; pass `null` for non-admins or when the list is unavailable.
 */
export function visibleTeams(me: MeRead, listed: readonly TeamRead[] | null): VisibleTeam[] {
  const mine: VisibleTeam[] = me.memberships.map(({ team, role }) => ({ team, role }))
  if (listed === null) return mine
  const memberOf = new Set(mine.map(({ team }) => team.id))
  const others = listed
    .filter((team) => !memberOf.has(team.id))
    .toSorted((a, b) => a.name.localeCompare(b.name))
    .map((team) => ({ team, role: null }))
  return [...mine, ...others]
}

/** The team with `slug` among `teams`, if any. */
export function findTeam(teams: readonly VisibleTeam[], slug: string): VisibleTeam | undefined {
  return teams.find(({ team }) => team.slug === slug)
}

/** The slug of the team the user opened last in this browser, if storage holds one. */
export function readLastTeam(): string | null {
  try {
    return localStorage.getItem(LAST_TEAM_KEY)
  } catch {
    return null
  }
}

/** Remembers `slug` as the last team opened; does nothing when storage is unavailable. */
export function rememberTeam(slug: string): void {
  try {
    localStorage.setItem(LAST_TEAM_KEY, slug)
  } catch {
  }
}
