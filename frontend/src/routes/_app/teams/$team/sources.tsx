import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/teams/$team/sources')({
  staticData: { title: 'Sources' },
  component: () => <PlaceholderPage title="Sources" description="The systems that send events to this team, and their event schemas, will show here." />,
})
