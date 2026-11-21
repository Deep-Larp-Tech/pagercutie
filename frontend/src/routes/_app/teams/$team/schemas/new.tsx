import { createFileRoute } from '@tanstack/react-router'
import * as zod from 'zod'
import { NewSchemaPage } from '@/components/event-schemas/new-schema-page'

/** `from`: id of the schema a new version starts from; absent for a new schema name. */
const newSchemaSearch = zod.object({
  from: zod.string().optional().catch(undefined),
})

export const Route = createFileRoute('/_app/teams/$team/schemas/new')({
  staticData: { title: 'New event schema' },
  validateSearch: newSchemaSearch,
  component: NewSchemaRoute,
})

function NewSchemaRoute() {
  const { from } = Route.useSearch()
  // A new `from` starts a fresh form.
  return <NewSchemaPage key={from ?? 'new'} from={from} />
}
