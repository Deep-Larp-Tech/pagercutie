import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/components/shell/placeholder-page'

export const Route = createFileRoute('/_app/')({
  staticData: { title: 'Overview' },
  component: OverviewPage,
})

// Chunk 3 fills the overview with on-call cards and the alert feed.
function OverviewPage() {
  return (
    <PlaceholderPage
      title="Overview"
      description="Your on-call shifts and the open alerts across your teams will show here."
    />
  )
}
