import { Construction } from 'lucide-react'
import { EmptyState } from './empty-state'
import { PageHeader } from './page-header'

/** Props for `PlaceholderPage`. */
export interface PlaceholderPageProps {
  /** Page title. */
  title: string
  /** What the finished page will show, in one line. */
  description: string
}

/** A screen that a later chunk builds (docs/plans/frontend.md); keeps nav links type-checked until then. */
export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={title} />
      <EmptyState icon={Construction} title="This page isn't built yet." description={description} />
    </div>
  )
}
