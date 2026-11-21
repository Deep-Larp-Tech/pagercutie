import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/me/phone')({
  staticData: { title: 'Phone' },
  component: () => <PlaceholderPage title="Phone" description="The text messages and calls PagerCutie sends you will show here." />,
})
