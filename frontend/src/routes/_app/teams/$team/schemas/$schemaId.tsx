import { createFileRoute } from '@tanstack/react-router'
import { SchemaDetailPage } from '@/components/event-schemas/schema-detail-page'

export const Route = createFileRoute('/_app/teams/$team/schemas/$schemaId')({
  staticData: { title: 'Event schema' },
  component: SchemaDetailRoute,
})

function SchemaDetailRoute() {
  const { schemaId } = Route.useParams()
  return <SchemaDetailPage key={schemaId} schemaId={schemaId} />
}
