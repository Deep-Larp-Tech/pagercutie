import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/admin/teams')({
  staticData: { title: 'Teams' },
  component: () => <PlaceholderPage title="Teams" description="Every team, with its members, will show here." />,
})
