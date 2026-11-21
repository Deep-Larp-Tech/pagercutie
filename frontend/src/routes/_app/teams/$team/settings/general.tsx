import { createFileRoute } from '@tanstack/react-router'
import { GeneralSettings } from '@/components/team-settings/general-settings'

export const Route = createFileRoute('/_app/teams/$team/settings/general')({
  component: GeneralSettings,
})
