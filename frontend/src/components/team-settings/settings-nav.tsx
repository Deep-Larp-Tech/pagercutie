import { useId, type ComponentProps } from 'react'
import { createLink } from '@tanstack/react-router'
import { LayoutGroup, motion } from 'motion/react'
import { controlTransition, focusRing } from '@/components/ui/styles'
import { motionTokens } from '@/lib/motion'
import { cn } from '@/lib/utils'

function TabAnchor({ className, children, ...props }: ComponentProps<'a'>) {
  const active = props['aria-current'] === 'page'
  return (
    <a
      className={cn(
        'relative flex h-9 items-center px-1 font-medium text-muted-foreground',
        'hover:text-foreground data-[status=active]:text-foreground',
        controlTransition,
        focusRing,
        className,
      )}
      {...props}
    >
      {children}
      {active && (
        <motion.span
          layoutId="settings-tab"
          data-testid="settings-tab-underline"
          className="absolute inset-x-0 -bottom-px h-0.5 bg-primary"
          transition={motionTokens.spring}
        />
      )}
    </a>
  )
}

const TabLink = createLink(TabAnchor)

/** Props for `SettingsNav`. */
export interface SettingsNavProps {
  /** Slug of the team whose settings are open. */
  team: string
}

/** Links to the four team settings pages; a violet underline slides to the open one, which has `aria-current="page"`. */
export function SettingsNav({ team }: SettingsNavProps) {
  const layoutGroup = useId()
  return (
    <LayoutGroup id={layoutGroup}>
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
    </LayoutGroup>
  )
}
