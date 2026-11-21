import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { ArrowLeft, FileQuestion } from 'lucide-react'
import {
  getGetEventSchemaQueryOptions,
  getListEventSchemasQueryOptions,
} from '@/api/generated/event-schemas/event-schemas'
import type { EventSchemaRead } from '@/api/generated/model'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { useTeamConfig } from '@/components/sources/use-team-config'
import { Section, SectionError, SectionSkeleton } from '@/components/team-settings/section'
import { buttonVariants, focusRing } from '@/components/ui/styles'
import { unexpectedStatusMessage } from '@/lib/api'
import { fieldTree } from '@/lib/json-schema-tree'
import { OFFLINE, PAGE_LIMIT } from '@/lib/pagination'
import { cn } from '@/lib/utils'
import { FieldTree } from './field-tree'
import { SampleCheck } from './sample-check'
import { schemaLabel } from './use-team-schemas'

/** Props for `SchemaDetailPage`. */
export interface SchemaDetailPageProps {
  schemaId: string
}

/** `/teams/$team/schemas/$schemaId`: one schema version, its fields, its JSON Schema and "Check a sample". */
export function SchemaDetailPage({ schemaId }: SchemaDetailPageProps) {
  const { team } = useTeamConfig()
  const query = useQuery(getGetEventSchemaQueryOptions(schemaId))
  const back = (
    <Link
      to="/teams/$team/schemas"
      params={{ team: team.slug }}
      className={`inline-flex w-fit items-center gap-1 rounded-sm text-muted-foreground hover:text-foreground ${focusRing}`}
    >
      <ArrowLeft size={14} strokeWidth={1.75} aria-hidden />
      Event schemas
    </Link>
  )

  let body
  if (query.isPending) body = <SectionSkeleton rows={6} />
  else if (query.isError) body = <SectionError message={OFFLINE} onRetry={() => void query.refetch()} />
  else {
    const response = query.data
    switch (response.status) {
      case 200:
        body = <SchemaDetail schema={response.data} />
        break
      case 404:
        body = (
          <EmptyState
            icon={FileQuestion}
            role="alert"
            title="This schema doesn't exist"
            description="It may have been removed, or the link is wrong. Pick a schema from the list."
          />
        )
        break
      case 422:
        body = <SectionError message="Couldn't load this schema. Check the link and try again." />
        break
      case 401:
        body = null
        break
      default:
        body = <SectionError message={unexpectedStatusMessage(response)} onRetry={() => void query.refetch()} />
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {back}
      {body}
    </div>
  )
}

function SchemaDetail({ schema }: { schema: EventSchemaRead }) {
  const { team, canEdit } = useTeamConfig()
  const owned = schema.team_id === team.id
  const newVersion = (
    <Link
      to="/teams/$team/schemas/new"
      params={{ team: team.slug }}
      search={{ from: schema.id }}
      className={buttonVariants({ variant: 'secondary' })}
    >
      New version
    </Link>
  )

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <PageHeader
          title={schemaLabel(schema)}
          description={schema.description ?? undefined}
          actions={canEdit && owned ? newVersion : undefined}
        />
        <Versions schema={schema} />
        {!owned && (
          <p className="text-muted-foreground">Another team owns this schema. Rules in any team can use it.</p>
        )}
      </div>
      <div className="grid gap-8 lg:grid-cols-2">
        <Section title="Fields" description="What an event of this schema contains.">
          <FieldTree nodes={fieldTree(schema.json_schema)} />
        </Section>
        <Section title="JSON Schema" description="Draft 2020-12. A saved version never changes.">
          <pre
            aria-label="JSON Schema"
            className="max-h-[480px] overflow-auto rounded-md bg-muted px-3 py-2 font-mono text-[13px]/[20px]"
          >
            {JSON.stringify(schema.json_schema, null, 2)}
          </pre>
        </Section>
      </div>
      <Section title="Check a sample" description="See whether an event would pass this schema before a producer sends it.">
        <SampleCheck schemaId={schema.id} />
      </Section>
    </div>
  )
}

/** Links to every version of the schema's name (`GET /event-schemas?name=`); shows nothing until they load. */
function Versions({ schema }: { schema: EventSchemaRead }) {
  const { team } = useTeamConfig()
  const query = useQuery(
    getListEventSchemasQueryOptions({ name: schema.name, team_id: schema.team_id, limit: PAGE_LIMIT }),
  )
  if (query.data?.status !== 200 || query.data.data.length < 2) return null
  const versions = [...query.data.data].sort((a, b) => b.version - a.version)
  return (
    <nav aria-label="Versions" className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="text-[12px]/[16px] font-medium text-muted-foreground">Versions</span>
      {versions.map((version) => {
        const current = version.id === schema.id
        return (
          <Link
            key={version.id}
            to="/teams/$team/schemas/$schemaId"
            params={{ team: team.slug, schemaId: version.id }}
            aria-current={current ? 'page' : undefined}
            className={cn(
              'rounded-full px-2 font-mono text-[13px]/[20px]',
              current ? 'bg-accent text-primary' : 'text-muted-foreground hover:text-foreground',
              focusRing,
            )}
          >
            v{version.version}
          </Link>
        )
      })}
    </nav>
  )
}
