import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/teams/$team/runbooks')({
  staticData: { title: 'Runbooks' },
  component: () => <PlaceholderPage title="Runbooks" description="The team's runbooks and their steps will show here." />,
})
