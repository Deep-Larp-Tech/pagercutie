import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/admin/users')({
  staticData: { title: 'Users' },
  component: () => <PlaceholderPage title="Users" description="Every user, their global role and their teams will show here." />,
})
