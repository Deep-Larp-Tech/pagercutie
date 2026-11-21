import { createFileRoute } from '@tanstack/react-router'
import { SchemasPage } from '@/components/event-schemas/schemas-page'

export const Route = createFileRoute('/_app/teams/$team/schemas/')({
  staticData: { title: 'Event schemas' },
  component: SchemasPage,
})
