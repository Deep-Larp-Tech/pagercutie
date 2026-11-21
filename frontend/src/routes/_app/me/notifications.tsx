import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/me/notifications')({
  staticData: { title: 'Notifications' },
  component: () => <PlaceholderPage title="Notifications" description="Which channels reach you, for which severities and at which times, will show here." />,
})
