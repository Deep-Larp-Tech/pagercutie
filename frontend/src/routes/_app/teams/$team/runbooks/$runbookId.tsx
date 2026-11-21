import { createFileRoute } from '@tanstack/react-router'
import { RunbookPage } from '@/components/runbooks/runbook-page'

export const Route = createFileRoute('/_app/teams/$team/runbooks/$runbookId')({
  staticData: { title: 'Runbook' },
  component: RunbookRoute,
})

function RunbookRoute() {
  const { runbookId } = Route.useParams()
  return <RunbookPage key={runbookId} runbookId={runbookId} />
}
