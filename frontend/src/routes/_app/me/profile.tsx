import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/me/profile')({
  staticData: { title: 'Profile' },
  component: () => <PlaceholderPage title="Profile" description="Your name, phone number and time zone will show here." />,
})
