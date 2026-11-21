import { createFileRoute } from '@tanstack/react-router'
import { NotificationSettings } from '@/components/team-settings/notification-settings'

export const Route = createFileRoute('/_app/teams/$team/settings/notifications')({
  component: NotificationSettings,
})
