import { useId, type ComponentProps, type ReactNode } from 'react'
import { createLink, Link } from '@tanstack/react-router'
import { LayoutGroup, motion } from 'motion/react'
import {
  Bell,
  BellRing,
  BookOpen,
  Braces,
  LayoutDashboard,
  ListFilter,
  Plug,
  Settings,
  Smartphone,
  UserRound,
  UsersRound,
} from 'lucide-react'
import { Logo } from '@/components/brand/Logo'
import { useVisibleTeams } from '@/hooks/use-visible-teams'
import { motionTokens } from '@/lib/motion'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'
import { controlTransition, focusRing } from '@/components/ui/styles'
import { cn } from '@/lib/utils'
import { TeamSwitcher } from './team-switcher'

const icon = { strokeWidth: 1.75, 'aria-hidden': true } as const

function NavAnchor({ className, children, ...props }: ComponentProps<'a'>) {
  // `Link` sets `aria-current="page"` (and `data-status`) on the active item.
  const active = props['aria-current'] === 'page'
  return (
    <a
      className={cn(
        'relative isolate flex h-8 items-center gap-2.5 rounded-md px-2.5 font-medium text-muted-foreground',
        'hover:bg-accent hover:text-foreground',
        // Violet marks the active nav item (DESIGN.md §4.1); its background is the sliding highlight below.
        'data-[status=active]:text-primary data-[status=active]:hover:bg-transparent',
        '[&_svg]:size-4 [&_svg]:shrink-0',
        controlTransition,
        focusRing,
        className,
      )}
      {...props}
    >
      {active && (
        <motion.span
          layoutId="nav-highlight"
          data-testid="nav-highlight"
          className="absolute inset-0 -z-10 rounded-md bg-accent"
          transition={motionTokens.spring}
        />
      )}
      {children}
    </a>
  )
}

/** Sidebar link with the router's typed `to` and `params`; the active one turns violet. */
const NavLink = createLink(NavAnchor)

function NavSection({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      {label !== undefined && (
        <h2 className="px-2.5 pb-1 text-[12px]/[16px] font-medium text-muted-foreground">{label}</h2>
      )}
      {children}
    </div>
  )
}

/** Props for `Sidebar`. */
export interface SidebarProps {
  /** Called when a link or the team switcher navigates, so the mobile sheet can close. */
  onNavigate?: () => void
}

/** App navigation: overview and phone, the current team's pages, the user's own pages, and admin pages for admins. */
export function Sidebar({ onNavigate }: SidebarProps) {
  const me = useMe()
  const { teams, list, current: team } = useVisibleTeams()
  const isAdmin = can(me, 'users-and-teams.manage')
  // The desktop sidebar and the mobile sheet can be mounted together; each keeps its own sliding highlight.
  const layoutGroup = useId()

  return (
    <LayoutGroup id={layoutGroup}>
      <div className="flex h-full flex-col">
        <div className="flex h-14 shrink-0 items-center px-4">
          <Link to="/" onClick={onNavigate} className={`rounded-md ${focusRing}`}>
            <Logo height={24} />
          </Link>
        </div>
        <nav aria-label="Main" className="flex flex-1 flex-col gap-6 overflow-y-auto px-3 pt-2 pb-6">
          <NavSection>
            <NavLink to="/" activeOptions={{ exact: true }} onClick={onNavigate}>
              <LayoutDashboard {...icon} />
              Overview
            </NavLink>
            <NavLink to="/me/phone" onClick={onNavigate}>
              <Smartphone {...icon} />
              Phone
            </NavLink>
          </NavSection>

          <NavSection label="Team">
            {team === undefined && list.kind === 'loading' ? null : team === undefined ? (
              <p className="px-2.5 text-[12px]/[16px] text-muted-foreground">
                {isAdmin
                  ? "You're not in a team yet. Add teams under Admin."
                  : "You're not in a team yet. Ask an admin to add you."}
              </p>
            ) : (
              <>
                <div className="pb-1.5">
                  <TeamSwitcher current={team} teams={teams} list={list} onNavigate={onNavigate} />
                </div>
                {can(me, 'team.read', team.team.id) && (
                  <>
                    <NavLink to="/teams/$team/alerts" params={{ team: team.team.slug }} onClick={onNavigate}>
                      <Bell {...icon} />
                      Alerts
                    </NavLink>
                    <NavLink to="/teams/$team/rules" params={{ team: team.team.slug }} onClick={onNavigate}>
                      <ListFilter {...icon} />
                      Rules
                    </NavLink>
                    <NavLink to="/teams/$team/runbooks" params={{ team: team.team.slug }} onClick={onNavigate}>
                      <BookOpen {...icon} />
                      Runbooks
                    </NavLink>
                    <NavLink to="/teams/$team/sources" params={{ team: team.team.slug }} onClick={onNavigate}>
                      <Plug {...icon} />
                      Sources
                    </NavLink>
                    <NavLink to="/teams/$team/schemas" params={{ team: team.team.slug }} onClick={onNavigate}>
                      <Braces {...icon} />
                      Schemas
                    </NavLink>
                    <NavLink to="/teams/$team/settings" params={{ team: team.team.slug }} onClick={onNavigate}>
                      <Settings {...icon} />
                      Settings
                    </NavLink>
                  </>
                )}
              </>
            )}
          </NavSection>

          <NavSection label="Me">
            <NavLink to="/me/rules" onClick={onNavigate}>
              <ListFilter {...icon} />
              My rules
            </NavLink>
            <NavLink to="/me/notifications" onClick={onNavigate}>
              <BellRing {...icon} />
              Notifications
            </NavLink>
          </NavSection>

          {isAdmin && (
            <NavSection label="Admin">
              <NavLink to="/admin/users" onClick={onNavigate}>
                <UserRound {...icon} />
                Users
              </NavLink>
              <NavLink to="/admin/teams" onClick={onNavigate}>
                <UsersRound {...icon} />
                Teams
              </NavLink>
            </NavSection>
          )}
        </nav>
      </div>
    </LayoutGroup>
  )
}
