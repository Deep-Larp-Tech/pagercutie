import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/teams/$team/alerts')({
  staticData: { title: 'Alerts' },
  component: () => <PlaceholderPage title="Alerts" description="The team's live alert feed will show here." />,
})
