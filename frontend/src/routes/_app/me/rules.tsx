import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/me/rules')({
  staticData: { title: 'My rules' },
  component: () => <PlaceholderPage title="My rules" description="Rules that alert only you will show here." />,
})
