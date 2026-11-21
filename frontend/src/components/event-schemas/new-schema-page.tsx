import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'
import { useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import {
  getGetEventSchemaQueryOptions,
  getListEventSchemasQueryKey,
  getListEventSchemasQueryOptions,
  useCreateEventSchema,
} from '@/api/generated/event-schemas/event-schemas'
import {
  createEventSchemaBodyDescriptionOneMax,
  createEventSchemaBodyNameMax,
  createEventSchemaBodyNameRegExp,
} from '@/api/generated/event-schemas/event-schemas.zod'
import type { EventSchemaRead } from '@/api/generated/model'
import { PageHeader } from '@/components/shell/page-header'
import { useTeamConfig } from '@/components/sources/use-team-config'
import { FormError, Section, SectionError, SectionSkeleton } from '@/components/team-settings/section'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { buttonVariants, focusRing } from '@/components/ui/styles'
import { unexpectedStatusMessage } from '@/lib/api'
import { fieldTree } from '@/lib/json-schema-tree'
import { describeParseError, isJsonObject, parseJson, type JsonObject } from '@/lib/json-text'
import { OFFLINE, PAGE_LIMIT } from '@/lib/pagination'
import { bodyIssues } from '@/lib/validation-errors'
import { FieldTree } from './field-tree'
import { JsonEditor } from './json-editor'
import { schemaLabel } from './use-team-schemas'

/** What a new schema name starts from: an object with one required string field. */
const STARTER = `{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "message": { "type": "string", "maxLength": 500 }
  },
  "required": ["message"]
}
`

const NAME_INVALID = 'Use lower case letters and digits, joined by single hyphens, at most 50 characters.'
const NOT_AN_OBJECT = 'A JSON Schema is a JSON object, wrapped in { }.'

const schemaForm = z.object({
  name: z
    .string()
    .min(1, 'Enter a schema name.')
    .max(createEventSchemaBodyNameMax, NAME_INVALID)
    .regex(createEventSchemaBodyNameRegExp, NAME_INVALID),
  description: z
    .string()
    .trim()
    .max(createEventSchemaBodyDescriptionOneMax, `Use at most ${createEventSchemaBodyDescriptionOneMax.toLocaleString('en')} characters.`),
  jsonText: z.string().superRefine((text, ctx) => {
    const parsed = parseJson(text)
    if (!parsed.ok) ctx.addIssue({ code: 'custom', message: describeParseError(parsed) })
    else if (!isJsonObject(parsed.value)) ctx.addIssue({ code: 'custom', message: NOT_AN_OBJECT })
  }),
})

type SchemaForm = z.infer<typeof schemaForm>

/** The JSON Schema in `text` when it is a JSON object, else `null`. */
function schemaObject(text: string): JsonObject | null {
  const parsed = parseJson(text)
  return parsed.ok && isJsonObject(parsed.value) ? parsed.value : null
}

/** Props for `NewSchemaPage`. */
export interface NewSchemaPageProps {
  /** Id of the version a new version starts from; `undefined` for a new schema name. */
  from: string | undefined
}

/** `/teams/$team/schemas/new`: a new schema name at version 1, or with `?from=` the next version of a name. */
export function NewSchemaPage({ from }: NewSchemaPageProps) {
  const { team } = useTeamConfig()
  return (
    <div className="flex flex-col gap-4">
      <Link
        to="/teams/$team/schemas"
        params={{ team: team.slug }}
        className={`inline-flex w-fit items-center gap-1 rounded-sm text-muted-foreground hover:text-foreground ${focusRing}`}
      >
        <ArrowLeft size={14} strokeWidth={1.75} aria-hidden />
        Event schemas
      </Link>
      {from === undefined ? <SchemaEditor base={null} version={1} /> : <NewVersion fromId={from} />}
    </div>
  )
}

/** Loads the version to start from and the name's latest version number, then shows the editor. */
function NewVersion({ fromId }: { fromId: string }) {
  const { team } = useTeamConfig()
  const base = useQuery(getGetEventSchemaQueryOptions(fromId))
  const name = base.data?.status === 200 ? base.data.data.name : undefined
  const versions = useQuery(
    getListEventSchemasQueryOptions({ name, team_id: team.id, limit: PAGE_LIMIT }, { query: { enabled: name !== undefined } }),
  )

  if (base.isPending) return <SectionSkeleton rows={6} />
  if (base.isError) return <SectionError message={OFFLINE} onRetry={() => void base.refetch()} />
  const response = base.data
  switch (response.status) {
    case 200:
      break
    case 404:
      return <SectionError message="The schema to start from doesn't exist. Pick one from the list." />
    case 422:
      return <SectionError message="Couldn't load the schema to start from. Check the link and try again." />
    case 401:
      return null
    default:
      return <SectionError message={unexpectedStatusMessage(response)} onRetry={() => void base.refetch()} />
  }
  const schema = response.data
  if (schema.team_id !== team.id) {
    return <SectionError message="Another team owns this schema, so only that team can add versions." />
  }

  if (versions.isPending) return <SectionSkeleton rows={6} />
  if (versions.isError) return <SectionError message={OFFLINE} onRetry={() => void versions.refetch()} />
  const listed = versions.data
  switch (listed.status) {
    case 200: {
      const latest = Math.max(schema.version, ...listed.data.map((version) => version.version))
      return <SchemaEditor base={schema} version={latest + 1} />
    }
    case 422:
      return <SectionError message="Couldn't find the latest version. Reload the page and try again." />
    case 401:
      return null
    default:
      return <SectionError message={unexpectedStatusMessage(listed)} onRetry={() => void versions.refetch()} />
  }
}

interface SchemaEditorProps {
  /** The version a new version starts from; `null` for a new name. */
  base: EventSchemaRead | null
  /** Version number the saved schema gets. */
  version: number
}

function SchemaEditor({ base, version }: SchemaEditorProps) {
  const { team } = useTeamConfig()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const create = useCreateEventSchema()
  const form = useForm<SchemaForm>({
    resolver: zodResolver(schemaForm),
    defaultValues: {
      name: base?.name ?? '',
      description: base?.description ?? '',
      jsonText: base === null ? STARTER : `${JSON.stringify(base.json_schema, null, 2)}\n`,
    },
    mode: 'onTouched',
  })
  const { errors, isSubmitting } = form.formState
  const jsonText = useWatch({ control: form.control, name: 'jsonText' })
  const preview = schemaObject(jsonText)
  const parsed = parseJson(jsonText)
  // Parse errors show while typing; server errors on the field come from `setError`.
  const liveError = parsed.ok ? (isJsonObject(parsed.value) ? undefined : NOT_AN_OBJECT) : describeParseError(parsed)

  const onSubmit = form.handleSubmit(async (values) => {
    const json_schema = schemaObject(values.jsonText)
    if (json_schema === null) return
    const data = {
      name: values.name,
      version,
      team_id: team.id,
      description: values.description === '' ? null : values.description,
      json_schema,
    }
    const response = await create.mutateAsync({ data }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 201:
        await queryClient.invalidateQueries({ queryKey: getListEventSchemasQueryKey() })
        toast.success(`${schemaLabel(response.data)} saved`)
        await navigate({
          to: '/teams/$team/schemas/$schemaId',
          params: { team: team.slug, schemaId: response.data.id },
        })
        return
      case 409:
        if (base === null) {
          form.setError('name', { message: 'A schema with this name already exists. Open it and add a version.' })
        } else {
          form.setError('root', {
            message: `Version ${version} already exists; someone saved it meanwhile. Reload the page to start from the latest.`,
          })
        }
        return
      case 422: {
        const issues = bodyIssues(response.data)
        if (issues.length === 0) form.setError('root', { message: "Couldn't save the schema. Check it and try again." })
        for (const { path, message } of issues) {
          const [field] = path
          if (field === 'name' || field === 'description') form.setError(field, { message })
          else if (field === 'json_schema') form.setError('jsonText', { message })
          else form.setError('root', { message })
        }
        return
      }
      case 400:
        form.setError('root', { message: "Couldn't read the schema. Reload the page and try again." })
        return
      case 403:
        form.setError('root', { message: 'Only members and leads can add event schemas.' })
        return
      case 401:
        return
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  })

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-6">
      <PageHeader
        title={base === null ? 'New event schema' : `New version of ${base.name}`}
        description={
          base === null
            ? 'Describe the events a source sends, as JSON Schema draft 2020-12.'
            : `Starts from version ${base.version}. Rules and sources keep using the versions they name.`
        }
      />
      <FieldGroup className="max-w-[480px]">
        {base === null ? (
          <Field invalid={errors.name !== undefined}>
            <FieldLabel>Name</FieldLabel>
            <Input autoComplete="off" spellCheck={false} autoFocus className="font-mono text-[13px]" {...form.register('name')} />
            <FieldDescription>Lower case, e.g. payment-failed. Versions of this schema keep the name.</FieldDescription>
            {errors.name?.message !== undefined && <FieldError>{errors.name.message}</FieldError>}
          </Field>
        ) : (
          errors.name?.message !== undefined && <FormError>{errors.name.message}</FormError>
        )}
        <dl className="grid grid-cols-[80px_1fr] gap-x-4 gap-y-1">
          {base !== null && (
            <>
              <dt className="text-muted-foreground">Name</dt>
              <dd className="font-mono text-[13px]/[20px]">{base.name}</dd>
            </>
          )}
          <dt className="text-muted-foreground">Version</dt>
          <dd className="font-mono text-[13px]/[20px]">{version}</dd>
        </dl>
        <Field invalid={errors.description !== undefined}>
          <FieldLabel>Description</FieldLabel>
          <Input autoComplete="off" {...form.register('description')} />
          <FieldDescription>Optional. Which events follow this schema, in one line.</FieldDescription>
          {errors.description?.message !== undefined && <FieldError>{errors.description.message}</FieldError>}
        </Field>
      </FieldGroup>
      <div className="grid gap-8 lg:grid-cols-2">
        <JsonEditor
          label="JSON Schema"
          description="Nested objects, arrays, $defs with $ref, and constraints such as maxLength or minimum."
          rows={20}
          error={errors.jsonText?.message ?? liveError}
          {...form.register('jsonText')}
        />
        <Section title="Fields" description="Updates as you type.">
          {preview === null ? (
            <p className="text-muted-foreground">Fix the JSON to see the fields.</p>
          ) : (
            <FieldTree nodes={fieldTree(preview)} />
          )}
        </Section>
      </div>
      {errors.root?.message !== undefined && <FormError>{errors.root.message}</FormError>}
      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Saving…' : base === null ? 'Save schema' : 'Save version'}
        </Button>
        <Link to="/teams/$team/schemas" params={{ team: team.slug }} className={buttonVariants({ variant: 'secondary' })}>
          Cancel
        </Link>
      </div>
    </form>
  )
}
