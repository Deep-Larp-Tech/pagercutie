import { createFileRoute } from '@tanstack/react-router'
import { TeamsPage } from '@/components/admin/teams-page'

export const Route = createFileRoute('/_app/admin/teams')({
  staticData: { title: 'Teams' },
  component: TeamsPage,
})
