import { createFileRoute } from '@tanstack/react-router'
import { SourcesPage } from '@/components/sources/sources-page'

export const Route = createFileRoute('/_app/teams/$team/sources')({
  staticData: { title: 'Sources' },
  component: SourcesPage,
})
