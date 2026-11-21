import { Link } from '@tanstack/react-router'
import { Braces } from 'lucide-react'
import {
  getListEventSchemasQueryKey,
  listEventSchemas,
  type listEventSchemasResponse,
} from '@/api/generated/event-schemas/event-schemas'
import type { EventSchemaRead } from '@/api/generated/model'
import { ListFailed, ShowMore, SkeletonRows } from '@/components/admin/list-parts'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { READ_ONLY_NOTICE, useTeamConfig } from '@/components/sources/use-team-config'
import { buttonVariants, focusRing } from '@/components/ui/styles'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { unexpectedStatusMessage } from '@/lib/api'
import { useOffsetPages, type PageResult } from '@/lib/pagination'
import { groupByName } from './use-team-schemas'

const COLUMNS = 3

/** Reads one `GET /event-schemas` page. */
function readSchemasPage(response: listEventSchemasResponse): PageResult<EventSchemaRead> {
  switch (response.status) {
    case 200:
      return { kind: 'items', items: response.data }
    case 401:
      return { kind: 'silent' }
    case 422:
      return { kind: 'failed', message: 'The list request was not valid. Reload the page and try again.' }
    default:
      return { kind: 'failed', message: unexpectedStatusMessage(response) }
  }
}

const linkClass = `rounded-sm underline-offset-4 hover:text-primary hover:underline ${focusRing}`

/** `/teams/$team/schemas`: the team's event schemas grouped by name, each with its versions (`SCH-1`, `SCH-2`). */
export function SchemasPage() {
  const { team, canEdit } = useTeamConfig()
  const params = { team_id: team.id }
  const pages = useOffsetPages(
    [...getListEventSchemasQueryKey(params), 'pages'],
    (page, signal) => listEventSchemas({ ...params, ...page }, { signal }),
    readSchemasPage,
  )
  const { list } = pages
  const newSchema = (
    <Link to="/teams/$team/schemas/new" params={{ team: team.slug }} className={buttonVariants()}>
      New schema
    </Link>
  )

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Event schemas"
        description="The shapes of the events this team's sources send. Saved versions never change."
        actions={canEdit ? newSchema : undefined}
      />
      {!canEdit && <p className="text-muted-foreground">{READ_ONLY_NOTICE}</p>}
      {list.kind === 'failed' ? (
        <ListFailed title="Couldn't load event schemas" message={list.message} onRetry={pages.retry} />
      ) : list.kind === 'listed' && list.items.length === 0 ? (
        <EmptyState
          icon={Braces}
          title="No event schemas yet"
          description={
            canEdit
              ? 'Describe the events a source sends with New schema.'
              : 'Members and leads describe the events this team receives.'
          }
        />
      ) : (
        <Table aria-label="Event schemas" aria-busy={list.kind === 'loading'}>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Versions</TableHead>
              <TableHead>Description</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.kind === 'loading' ? (
              <SkeletonRows columns={COLUMNS} />
            ) : (
              groupByName(list.items).map(({ name, versions }) => (
                <TableRow key={name}>
                  <TableCell>
                    <Link
                      to="/teams/$team/schemas/$schemaId"
                      params={{ team: team.slug, schemaId: versions[0].id }}
                      className={`font-mono text-[13px]/[20px] font-medium ${linkClass}`}
                    >
                      {name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <ul aria-label={`Versions of ${name}`} className="flex flex-wrap gap-x-2">
                      {versions.map((schema, index) => (
                        <li key={schema.id}>
                          <Link
                            to="/teams/$team/schemas/$schemaId"
                            params={{ team: team.slug, schemaId: schema.id }}
                            aria-label={`${name} version ${schema.version}${index === 0 ? ', latest' : ''}`}
                            className={`font-mono text-[13px]/[20px] text-muted-foreground ${linkClass}`}
                          >
                            v{schema.version}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </TableCell>
                  <TableCell className="max-w-80 truncate text-muted-foreground">{versions[0].description}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
      <ShowMore pages={pages} />
    </div>
  )
}
