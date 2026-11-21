import { createFileRoute } from '@tanstack/react-router'
import { MembersSettings } from '@/components/team-settings/members-settings'

export const Route = createFileRoute('/_app/teams/$team/settings/members')({
  component: MembersSettings,
})
