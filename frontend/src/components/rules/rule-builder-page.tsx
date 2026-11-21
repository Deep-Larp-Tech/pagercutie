import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useBlocker } from '@tanstack/react-router'
import { Braces, ShieldBan, X } from 'lucide-react'
import { toast } from 'sonner'
import { Colour, Severity, type EventSchemaRead, type RuleRead } from '@/api/generated/model'
import { getListEventSchemasQueryOptions } from '@/api/generated/event-schemas/event-schemas'
import { getListRunbooksQueryOptions } from '@/api/generated/runbooks/runbooks'
import {
  getGetRuleQueryKey,
  getGetRuleQueryOptions,
  getListRulesQueryKey,
  useCreateRule,
  useDeleteRule,
  useUpdateRule,
} from '@/api/generated/rules/rules'
import { createRuleBodyDedupFieldsMax, createRuleBodyPresentationFieldsMax } from '@/api/generated/rules/rules.zod'
import { FormError } from '@/components/admin/list-parts'
import { EmptyState } from '@/components/shell/empty-state'
import { NotFoundPage } from '@/components/shell/not-found-page'
import { PageHeader } from '@/components/shell/page-header'
import { Section, SectionError, SectionSkeleton } from '@/components/team-settings/section'
import { Button } from '@/components/ui/button'
import { Combobox, ComboboxContent, ComboboxInput, ComboboxItem } from '@/components/ui/combobox'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { buttonVariants } from '@/components/ui/styles'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { unexpectedStatusMessage } from '@/lib/api'
import { mergeFields, type EventField } from '@/lib/event-fields'
import { PAGE_LIMIT } from '@/lib/pagination'
import { toRootCondition } from '@/lib/rule-condition'
import {
  draftFromRule,
  newDraft,
  NO_ERRORS,
  placeIssues,
  toCreate,
  toUpdate,
  validateDraft,
  withSeverity,
  type DraftErrors,
  type RuleDraft,
  type WindowUnit,
} from '@/lib/rule-draft'
import { alertColourClass, severityIcon, severityLabel } from '@/lib/severity'
import { sampleEvent, type SampleEvent } from '@/lib/rule-sample'
import { insertPlaceholder } from '@/lib/templates'
import { cn } from '@/lib/utils'
import { bodyIssues } from '@/lib/validation-errors'
import { ConditionEditor } from './condition-editor'
import { BODY_UNREADABLE, forbiddenMessage, LOAD_REJECTED, OFFLINE, RULE_GONE } from './messages'
import { PathListInput } from './path-list-input'
import { RecipientsEditor } from './recipients-editor'
import { RulePreview } from './rule-preview'
import { RuleLink } from './rule-link'
import { defaultRecipients, ownedByScope, scopeOwner, useToRuleList, type RuleScope } from './rule-scope'
import { RuleTestPanel } from './rule-test-panel'

/** Most severe first, as people read the list. */
const SEVERITIES: readonly Severity[] = ['critical', 'error', 'warn', 'info', 'debug']
const severityItems = SEVERITIES.map((value) => ({ value, label: severityLabel[value] }))

/** Name of each rule colour in the picker. */
const colourLabel = {
  red: 'Red',
  orange: 'Orange',
  yellow: 'Yellow',
  green: 'Green',
  blue: 'Blue',
  grey: 'Grey',
} as const satisfies Record<Colour, string>
const colourItems = Object.values(Colour).map((value) => ({ value, label: colourLabel[value] }))

const windowUnitLabel = {
  seconds: 'seconds',
  minutes: 'minutes',
  hours: 'hours',
} as const satisfies Record<WindowUnit, string>
const windowUnitItems = (['seconds', 'minutes', 'hours'] as const).map((value) => ({ value, label: windowUnitLabel[value] }))

const NO_RUNBOOK = 'none'

/** `/teams/$team/rules/new` and `/me/rules/new`: the builder for a new rule. */
export function NewRulePage({ scope }: { scope: RuleScope }) {
  if (!scope.canEdit) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="New rule" />
        <EmptyState
          icon={ShieldBan}
          role="alert"
          title="You can't add rules here"
          description={forbiddenMessage(scope)}
          action={
            <RuleLink scope={scope} to={null} className={buttonVariants({ variant: 'secondary' })}>
              Back to rules
            </RuleLink>
          }
        />
      </div>
    )
  }
  return <RuleBuilder scope={scope} saved={null} />
}

/** `/teams/$team/rules/$ruleId` and `/me/rules/$ruleId`: loads the rule, then the builder. */
export function EditRulePage({ scope, ruleId }: { scope: RuleScope; ruleId: string }) {
  const query = useQuery(getGetRuleQueryOptions(ruleId))
  let body: ReactNode
  if (query.isPending) body = <SectionSkeleton rows={6} />
  else if (query.isError) body = <SectionError message={OFFLINE} onRetry={() => void query.refetch()} />
  else {
    const response = query.data
    switch (response.status) {
      case 200:
        if (!ownedByScope(scope, response.data.owner)) return <NotFoundPage />
        return <RuleBuilder key={response.data.id} scope={scope} saved={response.data} />
      case 401:
        body = null
        break
      case 404:
        body = <SectionError message={RULE_GONE} />
        break
      case 422:
        body = <SectionError message={LOAD_REJECTED} />
        break
      default:
        body = <SectionError message={unexpectedStatusMessage(response)} onRetry={() => void query.refetch()} />
    }
  }
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Rule" />
      {body}
    </div>
  )
}

interface RuleBuilderProps {
  scope: RuleScope
  /** The rule being edited; `null` for a new one. */
  saved: RuleRead | null
}

/** Event schemas for the schema picker and field suggestions; anyone may read every schema (DOMAIN.md §4). */
const schemasQueryOptions = getListEventSchemasQueryOptions({ limit: PAGE_LIMIT })

function RuleBuilder({ scope, saved: initial }: RuleBuilderProps) {
  const queryClient = useQueryClient()
  const toList = useToRuleList(scope)
  const createRule = useCreateRule()
  const updateRule = useUpdateRule()
  const [saved, setSaved] = useState(initial)
  const [draft, setDraft] = useState<RuleDraft>(() => (initial === null ? newDraft(defaultRecipients(scope)) : draftFromRule(initial)))
  const [snapshot, setSnapshot] = useState(() => JSON.stringify(draft))
  const [errors, setErrors] = useState<DraftErrors>(NO_ERRORS)
  const [sample, setSample] = useState<SampleEvent>({ payload: '', source: 'test', severity: 'critical' })
  const [deleting, setDeleting] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const leaving = useRef(false)
  const readOnly = !scope.canEdit
  const dirty = !readOnly && JSON.stringify(draft) !== snapshot

  const dirtyRef = useRef(dirty)
  useEffect(() => {
    dirtyRef.current = dirty
  }, [dirty])
  const blocker = useBlocker({
    shouldBlockFn: () => dirtyRef.current && !leaving.current,
    enableBeforeUnload: () => dirtyRef.current && !leaving.current,
    withResolver: true,
  })

  const schemas = useQuery(schemasQueryOptions)
  const schemaList = schemas.data?.status === 200 ? schemas.data.data : null
  const selectedSchemas = (schemaList ?? []).filter((schema) => draft.schemaIds.includes(schema.id))
  const fields = mergeFields(selectedSchemas.map((schema) => schema.json_schema))
  const condition = toRootCondition(draft.condition)
  const event = sampleEvent(sample, draft.schemaIds[0] ?? null)

  const change = (next: Partial<RuleDraft>) => setDraft((current) => ({ ...current, ...next }))

  const invalidate = async (ruleId: string | null) => {
    await queryClient.invalidateQueries({ queryKey: getListRulesQueryKey() })
    if (ruleId !== null) await queryClient.invalidateQueries({ queryKey: getGetRuleQueryKey(ruleId) })
  }

  const leave = async () => {
    leaving.current = true
    await toList()
  }

  const submit = async () => {
    const result = validateDraft(draft)
    if (!result.ok) {
      setErrors({ ...result.errors, root: "Couldn't save the rule. Fix the highlighted fields and try again." })
      return
    }
    setErrors(NO_ERRORS)
    setSubmitting(true)
    try {
      if (saved === null) {
        const response = await createRule.mutateAsync({ data: toCreate(result.parts, scopeOwner(scope)) }).catch(() => null)
        if (response === null) return setErrors({ ...NO_ERRORS, root: OFFLINE })
        switch (response.status) {
          case 201:
            await invalidate(null)
            toast.success('Rule saved')
            await leave()
            return
          case 400:
            return setErrors({ ...NO_ERRORS, root: BODY_UNREADABLE })
          case 401:
            return
          case 403:
            return setErrors({ ...NO_ERRORS, root: `Couldn't save the rule. ${forbiddenMessage(scope)}` })
          case 404:
            return setErrors({
              ...NO_ERRORS,
              root: `Couldn't save the rule. Something it points at no longer exists: ${response.data.detail}`,
            })
          case 422:
            return setErrors(placeIssues(draft, bodyIssues(response.data)))
          default:
            return setErrors({ ...NO_ERRORS, root: `Couldn't save the rule. ${unexpectedStatusMessage(response)}` })
        }
      }
      const data = toUpdate(result.parts, saved)
      const response = await updateRule.mutateAsync({ ruleId: saved.id, data }).catch(() => null)
      if (response === null) return setErrors({ ...NO_ERRORS, root: OFFLINE })
      switch (response.status) {
        case 200: {
          await invalidate(saved.id)
          setSaved(response.data)
          setSnapshot(JSON.stringify(draft))
          toast.success('Rule saved')
          return
        }
        case 400:
          return setErrors({ ...NO_ERRORS, root: BODY_UNREADABLE })
        case 401:
          return
        case 403:
          return setErrors({ ...NO_ERRORS, root: `Couldn't save the rule. ${forbiddenMessage(scope)}` })
        case 404:
          return setErrors({ ...NO_ERRORS, root: `Couldn't save the rule. ${response.data.detail}` })
        case 422:
          return setErrors(placeIssues(draft, bodyIssues(response.data)))
        default:
          return setErrors({ ...NO_ERRORS, root: `Couldn't save the rule. ${unexpectedStatusMessage(response)}` })
      }
    } finally {
      setSubmitting(false)
    }
  }

  const fieldErrors = errors.fields
  const personal = scope.kind === 'personal'
  const title = saved === null ? (personal ? 'New personal rule' : 'New rule') : saved.name

  return (
    <form
      noValidate
      onSubmit={(formEvent) => {
        formEvent.preventDefault()
        void submit()
      }}
      className="flex flex-col gap-10"
    >
      <PageHeader
        title={title}
        description={
          personal
            ? 'A personal rule alerts only you, for events from the teams you belong to.'
            : `Decide which events of ${scope.team.name} raise an alert, who hears about it and how it looks.`
        }
      />
      {readOnly && <p className="text-muted-foreground">{forbiddenMessage(scope)}</p>}

      <fieldset disabled={readOnly} className="flex min-w-0 flex-col gap-10">
        <Section title="Name">
          <div className="flex max-w-[480px] flex-col gap-4">
            <Field invalid={fieldErrors.name !== undefined}>
              <FieldLabel>Rule name</FieldLabel>
              <Input value={draft.name} onChange={(e) => change({ name: e.target.value })} />
              <FieldDescription>Short and specific, e.g. Order settlement failed in prod.</FieldDescription>
              {fieldErrors.name !== undefined && <FieldError>{fieldErrors.name}</FieldError>}
            </Field>
            <Field invalid={fieldErrors.description !== undefined}>
              <FieldLabel>Description (optional)</FieldLabel>
              <Textarea rows={2} value={draft.description} onChange={(e) => change({ description: e.target.value })} />
              {fieldErrors.description !== undefined && <FieldError>{fieldErrors.description}</FieldError>}
            </Field>
            <label className="flex w-fit items-center gap-2">
              <Switch checked={draft.enabled} onCheckedChange={(enabled) => change({ enabled })} />
              Rule is on
            </label>
          </div>
        </Section>

        <Section title="When" description="Which events raise an alert. Every condition looks at one field of the event.">
          <SchemaPicker
            schemas={schemaList}
            loading={schemas.isPending}
            selected={draft.schemaIds}
            onSelected={(schemaIds) => change({ schemaIds })}
            readOnly={readOnly}
            error={fieldErrors.schemaIds}
          />
          <ConditionEditor
            value={draft.condition}
            onChange={(next) => change({ condition: next })}
            fields={fields}
            errors={errors.nodes}
            readOnly={readOnly}
          />
          <RuleTestPanel sample={sample} onSample={setSample} condition={condition} schemaId={draft.schemaIds[0] ?? null} readOnly={false} />
        </Section>

        <Section title="Who and how" description="Who gets the alert, and on which channels.">
          <RecipientsEditor
            scope={scope}
            recipients={draft.recipients}
            onRecipients={(recipients) => change({ recipients })}
            channels={draft.channels}
            onChannels={(channels) => change({ channels })}
            recipientsError={fieldErrors.recipients}
            channelsError={fieldErrors.channels}
            readOnly={readOnly}
          />
        </Section>

        <Section title="How it looks" description="What the alert says, and its severity and colour in the feed.">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <PresentationFields draft={draft} setDraft={setDraft} fields={fields} errors={fieldErrors} readOnly={readOnly} />
            <RulePreview draft={draft} teamId={scope.kind === 'team' ? scope.team.id : null} event={event} />
          </div>
        </Section>

        <Section
          title="Noise"
          description="Repeats of the same problem add to one alert's counter instead of raising new alerts."
        >
          <div className="flex flex-col gap-4">
            <PathListField
              title="Count as the same problem when these fields match"
              label="Fields that identify a problem"
              value={draft.dedupFields}
              onValueChange={(dedupFields) => change({ dedupFields })}
              fields={fields}
              max={createRuleBodyDedupFieldsMax}
              readOnly={readOnly}
              error={fieldErrors.dedupFields}
              description="With no fields, every matching event within the window is one alert. Pick payload.instrument to get one alert per instrument."
            />
            <Field invalid={fieldErrors.window !== undefined} className="w-auto">
              <FieldLabel>Group repeats for</FieldLabel>
              <div className="flex items-center gap-2">
                <Input
                  className="w-24"
                  inputMode="numeric"
                  value={draft.windowValue}
                  onChange={(e) => change({ windowValue: e.target.value })}
                />
                <Select
                  items={windowUnitItems}
                  value={draft.windowUnit}
                  onValueChange={(windowUnit) => windowUnit !== null && change({ windowUnit })}
                >
                  <SelectTrigger aria-label="Window unit" className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {windowUnitItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <FieldDescription>From the first event; up to 24 hours.</FieldDescription>
              {fieldErrors.window !== undefined && <FieldError>{fieldErrors.window}</FieldError>}
            </Field>
          </div>
        </Section>

        {scope.kind === 'team' && (
          <Section title="Runbook" description="Steps people follow, or that run on their own, when the alert fires.">
            <RunbookPicker
              teamId={scope.team.id}
              value={draft.runbookId}
              onValue={(runbookId) => change({ runbookId })}
              readOnly={readOnly}
              error={fieldErrors.runbook}
            />
          </Section>
        )}
      </fieldset>

      {errors.root !== null && <FormError>{errors.root}</FormError>}
      {!readOnly && (
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={submitting || (saved !== null && !dirty)}>
            {submitting ? 'Saving…' : 'Save rule'}
          </Button>
          <RuleLink scope={scope} to={null} className={buttonVariants({ variant: 'ghost' })}>
            {saved === null ? 'Cancel' : 'Back to rules'}
          </RuleLink>
          {saved !== null && (
            <Button type="button" variant="destructive" className="ml-auto" onClick={() => setDeleting(true)}>
              Delete rule
            </Button>
          )}
        </div>
      )}

      {saved !== null && (
        <DeleteRuleDialog
          rule={saved}
          scope={scope}
          open={deleting}
          onOpenChange={setDeleting}
          onDeleted={async () => {
            await invalidate(saved.id)
            await leave()
          }}
        />
      )}
      <ConfirmDialog
        open={blocker.status === 'blocked'}
        onOpenChange={(open) => !open && blocker.reset?.()}
        title="Leave without saving?"
        description="Your changes to this rule will be lost."
        confirmLabel="Discard changes"
        pendingLabel="Leaving…"
        pending={false}
        error={null}
        onConfirm={() => blocker.proceed?.()}
      />
    </form>
  )
}

interface SchemaPickerProps {
  /** `null` while loading or when `GET /event-schemas` failed. */
  schemas: EventSchemaRead[] | null
  loading: boolean
  selected: string[]
  onSelected: (ids: string[]) => void
  readOnly: boolean
  error?: string
}

function schemaName(schema: EventSchemaRead): string {
  return `${schema.name} v${schema.version}`
}

function SchemaPicker({ schemas, loading, selected, onSelected, readOnly, error }: SchemaPickerProps) {
  const [picking, setPicking] = useState<EventSchemaRead | null>(null)
  const options = (schemas ?? []).filter((schema) => !selected.includes(schema.id))
  return (
    <Field invalid={error !== undefined} className="max-w-[480px]">
      <FieldLabel>Event schemas</FieldLabel>
      {selected.length > 0 && (
        <ul aria-label="Selected event schemas" className="flex flex-wrap gap-1.5">
          {selected.map((id) => {
            const schema = schemas?.find((candidate) => candidate.id === id)
            const name = schema === undefined ? 'Unknown schema' : schemaName(schema)
            return (
              <li key={id} className="inline-flex h-6 items-center gap-1 rounded-full bg-muted pr-0.5 pl-2.5 font-mono text-[12px]/[16px]">
                {name}
                {!readOnly && (
                  <button
                    type="button"
                    aria-label={`Remove ${name}`}
                    className="flex size-5 items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
                    onClick={() => onSelected(selected.filter((other) => other !== id))}
                  >
                    <X className="size-3" strokeWidth={1.75} aria-hidden />
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {!readOnly && (
        <Combobox<EventSchemaRead>
          items={options}
          value={picking}
          onValueChange={(schema) => {
            setPicking(null)
            if (schema !== null) onSelected([...selected, schema.id])
          }}
          itemToStringLabel={schemaName}
          isItemEqualToValue={(a, b) => a.id === b.id}
        >
          <ComboboxInput placeholder="Add an event schema" />
          <ComboboxContent empty={loading ? 'Loading event schemas…' : schemas === null ? "Event schemas couldn't be loaded." : 'No other schema matches.'}>
            {(schema: EventSchemaRead) => (
              <ComboboxItem key={schema.id} value={schema}>
                <span className="font-mono text-[13px]">{schemaName(schema)}</span>
                {schema.description !== null && (
                  <span className="truncate text-[12px]/[16px] text-muted-foreground">{schema.description}</span>
                )}
              </ComboboxItem>
            )}
          </ComboboxContent>
        </Combobox>
      )}
      <FieldDescription>
        {schemas === null && !loading
          ? "Event schemas aren't available, so field suggestions cover source, severity and schema_id only. You can still type any field."
          : 'Leave empty to look at events of any schema. The schemas you pick suggest the fields below.'}
      </FieldDescription>
      {error !== undefined && <FieldError>{error}</FieldError>}
    </Field>
  )
}

interface PresentationFieldsProps {
  draft: RuleDraft
  setDraft: (update: (draft: RuleDraft) => RuleDraft) => void
  fields: readonly EventField[]
  errors: DraftErrors['fields']
  readOnly: boolean
}

function PresentationFields({ draft, setDraft, fields, errors, readOnly }: PresentationFieldsProps) {
  const titleRef = useRef<HTMLInputElement>(null)
  const bodyRef = useRef<HTMLTextAreaElement>(null)
  const insert = (target: 'title' | 'body', ref: RefObject<HTMLInputElement | HTMLTextAreaElement | null>, path: string) => {
    const element = ref.current
    const { text, caret } = insertPlaceholder(draft[target], path, element?.selectionStart ?? null)
    setDraft((current) => ({ ...current, [target]: text }))
    requestAnimationFrame(() => {
      element?.focus()
      element?.setSelectionRange(caret, caret)
    })
  }
  const SeverityIcon = severityIcon[draft.severity]
  return (
    <div className="flex flex-col gap-4">
      <Field invalid={errors.title !== undefined}>
        <div className="flex items-end justify-between gap-2">
          <FieldLabel>Title</FieldLabel>
          {!readOnly && <InsertField fields={fields} target="title" onInsert={(path) => insert('title', titleRef, path)} />}
        </div>
        <Input ref={titleRef} className="font-mono text-[13px]" value={draft.title} onChange={(e) => setDraft((current) => ({ ...current, title: e.target.value }))} />
        <FieldDescription>{'Put event values in with {{payload.field}}, e.g. Settlement {{payload.workflowId}} failed.'}</FieldDescription>
        {errors.title !== undefined && <FieldError>{errors.title}</FieldError>}
      </Field>
      <Field invalid={errors.body !== undefined}>
        <div className="flex items-end justify-between gap-2">
          <FieldLabel>Body (optional)</FieldLabel>
          {!readOnly && <InsertField fields={fields} target="body" onInsert={(path) => insert('body', bodyRef, path)} />}
        </div>
        <Textarea ref={bodyRef} rows={3} className="font-mono text-[13px]/[20px]" value={draft.body} onChange={(e) => setDraft((current) => ({ ...current, body: e.target.value }))} />
        {errors.body !== undefined && <FieldError>{errors.body}</FieldError>}
      </Field>
      <PathListField
        title="Fields shown on the alert"
        label="Fields on the alert"
        value={draft.fields}
        onValueChange={(next) => setDraft((current) => ({ ...current, fields: next }))}
        fields={fields}
        max={createRuleBodyPresentationFieldsMax}
        readOnly={readOnly}
        error={errors.fields}
      />
      <div className="flex flex-wrap gap-4">
        <Field className="w-auto" invalid={errors.severity !== undefined}>
          <FieldLabel>Severity</FieldLabel>
          <Select items={severityItems} value={draft.severity} onValueChange={(severity) => severity !== null && setDraft((current) => withSeverity(current, severity))}>
            <SelectTrigger className="w-40">
              <SeverityIcon strokeWidth={1.75} className="size-4 text-muted-foreground" aria-hidden />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {severityItems.map((item) => {
                const Icon = severityIcon[item.value]
                return (
                  <SelectItem key={item.value} value={item.value}>
                    <Icon strokeWidth={1.75} aria-hidden />
                    {item.label}
                  </SelectItem>
                )
              })}
            </SelectContent>
          </Select>
          {errors.severity !== undefined && <FieldError>{errors.severity}</FieldError>}
        </Field>
        <Field className="w-auto" invalid={errors.colour !== undefined}>
          <FieldLabel>Colour</FieldLabel>
          <Select
            items={colourItems}
            value={draft.colour}
            onValueChange={(colour) => colour !== null && setDraft((current) => ({ ...current, colour, colourTouched: true }))}
          >
            <SelectTrigger className="w-36">
              <span aria-hidden className={cn('size-3 rounded-full bg-c', alertColourClass[draft.colour])} />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {colourItems.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  <span aria-hidden className={cn('size-3 rounded-full bg-c', alertColourClass[item.value])} />
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FieldDescription>{draft.colourTouched ? 'Picked by hand.' : 'Follows the severity until you pick one.'}</FieldDescription>
          {errors.colour !== undefined && <FieldError>{errors.colour}</FieldError>}
        </Field>
      </div>
    </div>
  )
}

function InsertField({ fields, target, onInsert }: { fields: readonly EventField[]; target: 'title' | 'body'; onInsert: (path: string) => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button type="button" variant="ghost" size="sm" aria-label={`Insert a field into the ${target}`} />}>
        <Braces strokeWidth={1.75} aria-hidden />
        Insert field
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-72 overflow-y-auto">
        {fields.map((field) => (
          <DropdownMenuItem key={field.path} onClick={() => onInsert(field.path)} className="font-mono text-[13px]">
            {field.path}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

interface RunbookPickerProps {
  teamId: string
  value: string | null
  onValue: (runbookId: string | null) => void
  readOnly: boolean
  error?: string
}

function RunbookPicker({ teamId, value, onValue, readOnly, error }: RunbookPickerProps) {
  const query = useQuery(getListRunbooksQueryOptions({ team_id: teamId, limit: PAGE_LIMIT }))
  const runbooks = query.data?.status === 200 ? query.data.data : null
  const items = [
    { value: NO_RUNBOOK, label: 'No runbook' },
    ...(runbooks ?? []).map((runbook) => ({ value: runbook.id, label: runbook.title })),
  ]
  if (value !== null && !items.some((item) => item.value === value)) items.push({ value, label: 'Attached runbook' })
  return (
    <Field invalid={error !== undefined} className="w-auto">
      <FieldLabel>Runbook</FieldLabel>
      <Select
        items={items}
        value={value ?? NO_RUNBOOK}
        disabled={readOnly}
        onValueChange={(next) => next !== null && onValue(next === NO_RUNBOOK ? null : next)}
      >
        <SelectTrigger className="w-72">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {!query.isPending && runbooks === null && (
        <FieldDescription>Runbooks couldn't be loaded, so only the current choice is shown.</FieldDescription>
      )}
      {runbooks !== null && runbooks.length === 0 && <FieldDescription>This team has no runbooks yet.</FieldDescription>}
      {error !== undefined && <FieldError>{error}</FieldError>}
    </Field>
  )
}

interface DeleteRuleDialogProps {
  rule: RuleRead
  scope: RuleScope
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeleted: () => Promise<void>
}

function DeleteRuleDialog({ rule, scope, open, onOpenChange, onDeleted }: DeleteRuleDialogProps) {
  const deleteRule = useDeleteRule()
  const [error, setError] = useState<string | null>(null)

  const confirm = async () => {
    setError(null)
    const response = await deleteRule.mutateAsync({ ruleId: rule.id }).catch(() => null)
    if (response === null) return setError(OFFLINE)
    switch (response.status) {
      case 204:
        onOpenChange(false)
        toast.success('Rule deleted')
        return onDeleted()
      case 401:
        return
      case 403:
        return setError(`Couldn't delete the rule. ${forbiddenMessage(scope)}`)
      case 404:
        onOpenChange(false)
        return onDeleted()
      case 422:
        return setError("Couldn't delete the rule. Reload the page and try again.")
      default:
        return setError(`Couldn't delete the rule. ${unexpectedStatusMessage(response)}`)
    }
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        setError(null)
        onOpenChange(next)
      }}
      title={`Delete ${rule.name}?`}
      description="New events stop raising alerts from this rule. Alerts it already raised stay as they are."
      confirmLabel="Delete rule"
      pendingLabel="Deleting…"
      pending={deleteRule.isPending}
      error={error}
      onConfirm={() => void confirm()}
    />
  )
}

interface PathListFieldProps {
  /** Visible heading above the list. */
  title: string
  /** Accessible name of the list; the add input is "Add to <label>". */
  label: string
  value: string[]
  onValueChange: (paths: string[]) => void
  fields: readonly EventField[]
  max: number
  readOnly: boolean
  error?: string
  description?: string
}

function PathListField({ title, label, value, onValueChange, fields, max, readOnly, error, description }: PathListFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[14px]/[20px] font-medium">{title}</span>
      <PathListInput
        label={label}
        value={value}
        onValueChange={onValueChange}
        fields={fields}
        max={max}
        disabled={readOnly}
        invalid={error !== undefined}
      />
      {description !== undefined && <p className="text-[12px]/[16px] text-muted-foreground">{description}</p>}
      {error !== undefined && <p className="text-[12px]/[16px] font-medium text-alert-red-text">{error}</p>}
    </div>
  )
}
