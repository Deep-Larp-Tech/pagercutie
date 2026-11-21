import { createFileRoute } from '@tanstack/react-router'
import { AlertDetail } from '@/components/alert-detail/alert-detail'

export const Route = createFileRoute('/_app/alerts/$alertId')({
  staticData: { title: 'Alert' },
  component: AlertDetailPage,
})

/** `/alerts/$alertId`: one alert with its runbook steps, deliveries and history, for any role in its teams. */
function AlertDetailPage() {
  const { alertId } = Route.useParams()
  return <AlertDetail alertId={alertId} />
}
