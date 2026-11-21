import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/teams/$team/settings')({
  staticData: { title: 'Settings' },
  component: () => <PlaceholderPage title="Settings" description="The team's name, members, on-call rotation and notification settings will show here." />,
})
