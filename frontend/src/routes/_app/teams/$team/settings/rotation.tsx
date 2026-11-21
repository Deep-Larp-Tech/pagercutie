import { createFileRoute } from '@tanstack/react-router'
import { RotationSettings } from '@/components/team-settings/rotation-settings'

export const Route = createFileRoute('/_app/teams/$team/settings/rotation')({
  component: RotationSettings,
})
