import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/teams/$team/rules')({
  staticData: { title: 'Rules' },
  component: () => <PlaceholderPage title="Rules" description="The rules that turn this team's events into alerts will show here." />,
})
