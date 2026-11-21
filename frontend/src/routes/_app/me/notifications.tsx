import { createFileRoute } from '@tanstack/react-router'
import { MyNotifications } from '@/components/preferences/my-notifications'

export const Route = createFileRoute('/_app/me/notifications')({
  staticData: { title: 'Notifications' },
  component: MyNotifications,
})
