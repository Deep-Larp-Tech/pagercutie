import { createFileRoute } from '@tanstack/react-router'
import { NewRunbookPage } from '@/components/runbooks/new-runbook-page'

export const Route = createFileRoute('/_app/teams/$team/runbooks/new')({
  staticData: { title: 'New runbook' },
  component: NewRunbookPage,
})
