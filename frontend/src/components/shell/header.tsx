import type { ReactNode } from 'react'
import { useMatches } from '@tanstack/react-router'
import { motion } from 'motion/react'
import { CommandMenu } from '@/components/command-menu/command-menu'
import { screenEnter } from '@/lib/motion'
import { useVisibleTeams } from '@/hooks/use-visible-teams'
import { layers } from '@/lib/layers'
import { ThemeToggle } from './theme-toggle'
import { UserMenu } from './user-menu'

declare module '@tanstack/react-router' {
  interface StaticDataRouteOption {
    /** Page title the header shows for this route; the deepest matched route with one wins. */
    title?: string
    /** Child page changes animate inside this route's own outlet, so its chrome (a sub-nav) stays mounted. */
    ownsTransitions?: boolean
  }
}

/** Title of the deepest matched route that sets `staticData.title`, prefixed with the team name inside a team. */
function HeaderTitle() {
  const title = useMatches({
    select: (matches) => matches.findLast((match) => match.staticData.title !== undefined)?.staticData.title,
  })
  const teamName = useVisibleTeams().inUrl?.team.name
  if (title === undefined) return null
  return (
    <motion.p key={`${teamName ?? ''}/${title}`} className="min-w-0 truncate font-medium" {...screenEnter}>
      {teamName !== undefined && (
        <>
          <span className="text-muted-foreground">{teamName}</span>
          <span className="px-1.5 text-muted-foreground" aria-hidden>
            /
          </span>
        </>
      )}
      {title}
    </motion.p>
  )
}

/** Props for `Header`. */
export interface HeaderProps {
  /** Button that opens the navigation sheet; shown below 1024 px only. */
  navTrigger: ReactNode
}

/** Top bar of the shell: navigation button on small screens, page title, command menu, theme toggle and account menu. */
export function Header({ navTrigger }: HeaderProps) {
  return (
    <header
      className="sticky top-0 flex h-14 shrink-0 items-center gap-3 border-b bg-background px-4 sm:px-6 lg:px-8"
      style={{ zIndex: layers.header }}
    >
      <div className="lg:hidden">{navTrigger}</div>
      <HeaderTitle />
      <div className="ml-auto flex items-center gap-2">
        <CommandMenu />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  )
}
