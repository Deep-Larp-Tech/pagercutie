import { createFileRoute, Outlet } from '@tanstack/react-router'
import { SettingsNav } from '@/components/team-settings/settings-nav'
import { useTeamSettings } from '@/components/team-settings/use-team-settings'
import { PageHeader } from '@/components/shell/page-header'

/** Team settings: a sub-navigation over General, Members, Rotation and Notifications. Any team role may read them. */
export const Route = createFileRoute('/_app/teams/$team/settings')({
  staticData: { title: 'Settings' },
  component: SettingsLayout,
})

function SettingsLayout() {
  const { team, canEdit } = useTeamSettings()
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Settings" description={`Who is in ${team.name}, who is on call, and how the team is notified.`} />
      <SettingsNav team={team.slug} />
      {!canEdit && <p className="text-muted-foreground">Only team leads can change this.</p>}
      <Outlet />
    </div>
  )
}
