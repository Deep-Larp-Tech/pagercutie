import type { ComponentProps } from 'react'
import { createLink } from '@tanstack/react-router'
import { controlTransition, focusRing } from '@/components/ui/styles'
import { cn } from '@/lib/utils'

function TabAnchor({ className, ...props }: ComponentProps<'a'>) {
  return (
    <a
      className={cn(
        '-mb-px flex h-9 items-center border-b-2 border-transparent px-1 font-medium text-muted-foreground',
        'hover:text-foreground',
        // `Link` sets `data-status` and `aria-current` on the page that is open; violet marks it (DESIGN.md §4.1).
        'data-[status=active]:border-primary data-[status=active]:text-foreground',
        controlTransition,
        focusRing,
        className,
      )}
      {...props}
    />
  )
}

const TabLink = createLink(TabAnchor)

/** Props for `SettingsNav`. */
export interface SettingsNavProps {
  /** Slug of the team whose settings are open. */
  team: string
}

/** Links to the four team settings pages; the open one is underlined in violet and has `aria-current="page"`. */
export function SettingsNav({ team }: SettingsNavProps) {
  return (
    <nav aria-label="Team settings" className="flex gap-5 overflow-x-auto border-b">
      <TabLink to="/teams/$team/settings/general" params={{ team }}>
        General
      </TabLink>
      <TabLink to="/teams/$team/settings/members" params={{ team }}>
        Members
      </TabLink>
      <TabLink to="/teams/$team/settings/rotation" params={{ team }}>
        Rotation
      </TabLink>
      <TabLink to="/teams/$team/settings/notifications" params={{ team }}>
        Notifications
      </TabLink>
    </nav>
  )
}
