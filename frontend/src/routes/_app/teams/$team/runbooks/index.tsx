import { createFileRoute } from '@tanstack/react-router'
import { RunbooksPage } from '@/components/runbooks/runbooks-page'

export const Route = createFileRoute('/_app/teams/$team/runbooks/')({
  staticData: { title: 'Runbooks' },
  component: RunbooksPage,
})
