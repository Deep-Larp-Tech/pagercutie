import { useNavigate, useMatchRoute } from '@tanstack/react-router'
import { Check, ChevronsUpDown } from 'lucide-react'
import type { TeamRole } from '@/api/generated/model'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { TeamList, VisibleTeam } from '@/lib/teams'

/** Team pages the switcher keeps when it changes team, most specific first. */
const teamSections = [
  '/teams/$team/alerts',
  '/teams/$team/rules',
  '/teams/$team/runbooks',
  '/teams/$team/sources',
  '/teams/$team/settings',
] as const

type TeamSection = (typeof teamSections)[number]

const roleLabel = {
  lead: 'Lead',
  member: 'Member',
  viewer: 'Viewer',
} as const satisfies Record<TeamRole, string>

/** Props for `TeamSwitcher`. */
export interface TeamSwitcherProps {
  /** Team the sidebar's team links point at. */
  current: VisibleTeam
  /** Every team the user can open, memberships first. */
  teams: readonly VisibleTeam[]
  /** How the admin's `GET /teams` went; a documented failure shows one line in the menu. */
  list: TeamList
  /** Called after the switcher navigates, so the mobile sheet can close. */
  onNavigate?: () => void
}

/** Menu of the user's teams; picking one opens the same team page (Alerts from elsewhere) in that team. */
export function TeamSwitcher({ current, teams, list, onNavigate }: TeamSwitcherProps) {
  const navigate = useNavigate()
  const matchRoute = useMatchRoute()
  const section: TeamSection =
    teamSections.find((to) => matchRoute({ to, fuzzy: true }) !== false) ?? '/teams/$team/alerts'

  const mine = teams.filter(({ role }) => role !== null)
  const others = teams.filter(({ role }) => role === null)

  function open(slug: string) {
    void navigate({ to: section, params: { team: slug } })
    onNavigate?.()
  }

  function item({ team, role }: VisibleTeam) {
    const selected = team.id === current.team.id
    return (
      <DropdownMenuItem key={team.id} onClick={() => open(team.slug)} aria-current={selected ? 'true' : undefined}>
        <Check strokeWidth={1.75} className={selected ? 'text-primary!' : 'invisible'} aria-hidden />
        <span className="min-w-0 flex-1 truncate">{team.name}</span>
        {role !== null && <span className="text-[12px]/[16px] text-muted-foreground">{roleLabel[role]}</span>}
      </DropdownMenuItem>
    )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="secondary" className="w-full justify-between" aria-label={`Team: ${current.team.name}. Switch team`} />}
      >
        <span className="truncate">{current.team.name}</span>
        <ChevronsUpDown strokeWidth={1.75} className="text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-(--anchor-width) min-w-56">
        {mine.length > 0 && (
          <DropdownMenuGroup>
            <DropdownMenuLabel>Your teams</DropdownMenuLabel>
            {mine.map(item)}
          </DropdownMenuGroup>
        )}
        {mine.length > 0 && others.length > 0 && <DropdownMenuSeparator />}
        {others.length > 0 && (
          <DropdownMenuGroup>
            <DropdownMenuLabel>Other teams</DropdownMenuLabel>
            {others.map(item)}
          </DropdownMenuGroup>
        )}
        {list.kind === 'failed' && (
          <p role="alert" className="px-2 pt-2 pb-1.5 text-[12px]/[16px] text-muted-foreground">
            {list.message}
          </p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
