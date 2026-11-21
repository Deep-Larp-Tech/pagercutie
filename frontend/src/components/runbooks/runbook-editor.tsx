import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { Trash2 } from 'lucide-react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { RunbookFormat, type RunbookRead, type RunbookUpdate } from '@/api/generated/model'
import {
  getGetRunbookQueryKey,
  getListRunbooksQueryKey,
  useCreateRunbook,
  useUpdateRunbook,
  type getRunbookResponse,
} from '@/api/generated/runbooks/runbooks'
import {
  createRunbookBodyOriginalMax,
  createRunbookBodySlugMax,
  createRunbookBodySlugRegExp,
  createRunbookBodyTitleMax,
} from '@/api/generated/runbooks/runbooks.zod'
import { FormError } from '@/components/admin/list-parts'
import { PageHeader } from '@/components/shell/page-header'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { Textarea } from '@/components/ui/textarea'
import { buttonVariants } from '@/components/ui/styles'
import { useUnsavedChanges } from '@/hooks/use-unsaved-changes'
import { unexpectedStatusMessage } from '@/lib/api'
import { applyValidationErrors } from '@/lib/form-errors'
import { OFFLINE } from '@/lib/pagination'
import { runbookExamples, type RunbookExample } from '@/lib/runbook-examples'
import { runbookFormatInfo } from '@/lib/runbooks'
import { slugify } from '@/lib/slug'
import { DeleteRunbookDialog } from './delete-runbook-dialog'
import { InsertExampleMenu } from './insert-example-menu'
import { RUNBOOK_GONE, SAVE_FORBIDDEN, SAVE_REJECTED, SLUG_INVALID } from './messages'
import { ParsePreview } from './parse-preview'
import { useParsePreview } from './use-parse-preview'
import { useRunbookScope } from './use-runbook-scope'

const runbookSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, 'Enter a title.')
    .max(createRunbookBodyTitleMax, `Use at most ${createRunbookBodyTitleMax} characters.`),
  slug: z.string().min(1, 'Enter a slug.').max(createRunbookBodySlugMax, SLUG_INVALID).regex(createRunbookBodySlugRegExp, SLUG_INVALID),
  format: z.enum(RunbookFormat),
  original: z
    .string()
    .refine((value) => value.trim() !== '', 'Paste the runbook text or insert an example.')
    .refine(
      (value) => value.length <= createRunbookBodyOriginalMax,
      `Use at most ${createRunbookBodyOriginalMax.toLocaleString('en')} characters.`,
    ),
})

type Values = z.infer<typeof runbookSchema>

const FIELDS = ['title', 'slug', 'format', 'original'] as const satisfies readonly (keyof Values)[]

const formatOptions = Object.values(RunbookFormat).map((value) => ({ value, label: runbookFormatInfo[value].label }))

function valuesOf(runbook: RunbookRead): Values {
  return { title: runbook.title, slug: runbook.slug, format: runbook.format, original: runbook.original }
}

const EMPTY: Values = { title: '', slug: '', format: 'structured', original: '' }

/**
 * Create and edit form for a runbook: title, slug (follows the title until edited; fixed once saved), format,
 * the original text and a live parse preview next to it. Without `runbook` it creates (`POST /runbooks`), with one
 * it saves the changed fields (`PATCH /runbooks/{id}`). The condition is never sent: YAML sets it with `matches:`.
 */
export function RunbookEditor({ runbook }: { runbook?: RunbookRead }) {
  const { team } = useRunbookScope()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const createRunbook = useCreateRunbook()
  const updateRunbook = useUpdateRunbook()
  const form = useForm<z.input<typeof runbookSchema>, unknown, Values>({
    resolver: zodResolver(runbookSchema),
    defaultValues: runbook === undefined ? EMPTY : valuesOf(runbook),
  })
  const { errors, isDirty, isSubmitting } = form.formState
  const [format, original] = useWatch({ control: form.control, name: ['format', 'original'] })
  const preview = useParsePreview(format, original, runbook)
  const unsaved = useUnsavedChanges(isDirty)
  const [slugEdited, setSlugEdited] = useState(false)
  const [replacing, setReplacing] = useState<RunbookExample | null>(null)
  const [deleting, setDeleting] = useState(false)

  const titleField = form.register('title', {
    onChange: (event: { target: { value: string } }) => {
      if (runbook === undefined && !slugEdited) form.setValue('slug', slugify(event.target.value))
    },
  })
  const slugField = form.register('slug', { onChange: () => setSlugEdited(true) })

  function insertExample(example: RunbookExample) {
    const options = { shouldDirty: true, shouldValidate: form.formState.isSubmitted }
    form.setValue('format', example.format, options)
    form.setValue('original', example.original, options)
    if (form.getValues('title').trim() === '') {
      form.setValue('title', example.title, options)
      if (runbook === undefined && !slugEdited) form.setValue('slug', slugify(example.title), options)
    }
  }

  function pickExample(example: RunbookExample) {
    const text = form.getValues('original')
    const unchanged = text.trim() === '' || runbookExamples.some((candidate) => candidate.original === text)
    if (unchanged) insertExample(example)
    else setReplacing(example)
  }

  async function showSaved(saved: RunbookRead) {
    const cached: getRunbookResponse = { status: 200, data: saved, headers: new Headers() }
    queryClient.setQueryData(getGetRunbookQueryKey(saved.id), cached)
    await queryClient.invalidateQueries({ queryKey: getListRunbooksQueryKey() })
  }

  const onSubmit = form.handleSubmit(async (values) => {
    if (runbook === undefined) await create(values)
    else await update(runbook, values)
  })

  async function create(values: Values) {
    const response = await createRunbook
      .mutateAsync({ data: { ...values, team_id: team.id } })
      .catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 201:
        await showSaved(response.data)
        toast.success(`${response.data.title} saved`)
        unsaved.allowNextNavigation()
        await navigate({
          to: '/teams/$team/runbooks/$runbookId',
          params: { team: team.slug, runbookId: response.data.id },
          replace: true,
        })
        return
      case 409:
        form.setError('slug', { message: 'Another runbook already uses this slug. Pick another one.' })
        return
      case 422:
        applyValidationErrors(form.setError, response.data, FIELDS)
        return
      case 400:
        form.setError('root', { message: SAVE_REJECTED })
        return
      case 403:
        form.setError('root', { message: SAVE_FORBIDDEN })
        return
      case 404:
        form.setError('root', { message: 'This team no longer exists. Pick another team from the switcher.' })
        return
      case 401:
        return
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  }

  async function update(current: RunbookRead, values: Values) {
    const data: RunbookUpdate = {}
    if (values.title !== current.title) data.title = values.title
    if (values.format !== current.format) data.format = values.format
    if (values.original !== current.original) data.original = values.original
    const response = await updateRunbook.mutateAsync({ runbookId: current.id, data }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 200:
        form.reset(valuesOf(response.data))
        await showSaved(response.data)
        toast.success('Runbook saved')
        return
      case 422:
        applyValidationErrors(form.setError, response.data, FIELDS)
        return
      case 400:
        form.setError('root', { message: SAVE_REJECTED })
        return
      case 403:
        form.setError('root', { message: SAVE_FORBIDDEN })
        return
      case 404:
        form.setError('root', { message: RUNBOOK_GONE })
        return
      case 401:
        return
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={runbook?.title ?? 'New runbook'}
        description={
          runbook === undefined
            ? 'Paste a runbook as YAML, Markdown, free text or a link. The preview shows the steps PagerCutie reads from it.'
            : undefined
        }
        actions={
          runbook !== undefined && (
            <Button variant="secondary" onClick={() => setDeleting(true)}>
              <Trash2 strokeWidth={1.75} aria-hidden />
              Delete runbook
            </Button>
          )
        }
      />
      <div className="grid items-start gap-8 lg:grid-cols-2">
        <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex min-w-0 flex-col gap-5">
          <FieldGroup>
            <Field invalid={errors.title !== undefined}>
              <FieldLabel>Title</FieldLabel>
              <Input autoComplete="off" autoFocus={runbook === undefined} {...titleField} />
              {errors.title?.message !== undefined && <FieldError>{errors.title.message}</FieldError>}
            </Field>
            {runbook === undefined ? (
              <Field invalid={errors.slug !== undefined}>
                <FieldLabel>Slug</FieldLabel>
                <Input autoComplete="off" spellCheck={false} className="font-mono text-[13px]" {...slugField} />
                <FieldDescription>Rules and YAML refer to the runbook by it. It can't be changed later.</FieldDescription>
                {errors.slug?.message !== undefined && <FieldError>{errors.slug.message}</FieldError>}
              </Field>
            ) : (
              <div className="flex flex-col gap-1.5">
                <span className="text-[14px]/[20px] font-medium">Slug</span>
                <span className="font-mono text-[13px]/[20px] font-[450]">{runbook.slug}</span>
              </div>
            )}
            <div className="flex flex-col gap-1.5">
              <span className="text-[14px]/[20px] font-medium">Format</span>
              <Controller
                control={form.control}
                name="format"
                render={({ field }) => (
                  <SegmentedControl
                    aria-label="Format"
                    options={formatOptions}
                    value={field.value}
                    onValueChange={field.onChange}
                  />
                )}
              />
              <p className="text-[12px]/[16px] text-muted-foreground">{runbookFormatInfo[format].hint}</p>
              {errors.format?.message !== undefined && (
                <p className="text-[12px]/[16px] font-medium text-alert-red-text">{errors.format.message}</p>
              )}
            </div>
            <Field invalid={errors.original !== undefined}>
              <div className="flex items-end justify-between gap-3">
                <FieldLabel>Runbook text</FieldLabel>
                <InsertExampleMenu onPick={pickExample} />
              </div>
              <Textarea
                rows={16}
                spellCheck={false}
                className="min-h-64 resize-y py-2 font-mono text-[13px]/[20px] font-[450]"
                {...form.register('original')}
              />
              <FieldDescription>
                Use <code className="font-mono text-[13px]">{'{{payload.field}}'}</code> to fill in values from the
                event, e.g. <code className="font-mono text-[13px]">{'{{payload.workflowId}}'}</code>.
              </FieldDescription>
              {errors.original?.message !== undefined && <FieldError>{errors.original.message}</FieldError>}
            </Field>
          </FieldGroup>
          {errors.root?.message !== undefined && <FormError>{errors.root.message}</FormError>}
          <div className="flex items-center gap-2">
            <Button type="submit" disabled={isSubmitting || (runbook !== undefined && !isDirty)}>
              {isSubmitting ? 'Saving…' : 'Save runbook'}
            </Button>
            <Link to="/teams/$team/runbooks" params={{ team: team.slug }} className={buttonVariants({ variant: 'ghost' })}>
              Cancel
            </Link>
          </div>
        </form>
        <div className="min-w-0 rounded-xl border p-4 lg:sticky lg:top-20">
          <ParsePreview state={preview} />
        </div>
      </div>
      <ConfirmDialog
        open={replacing !== null}
        onOpenChange={(open) => !open && setReplacing(null)}
        title="Replace the runbook text?"
        description="The example replaces what you wrote in the text box."
        confirmLabel="Replace text"
        pendingLabel="Replacing…"
        pending={false}
        error={null}
        onConfirm={() => {
          if (replacing !== null) insertExample(replacing)
          setReplacing(null)
        }}
      />
      {runbook !== undefined && (
        <DeleteRunbookDialog
          runbook={runbook}
          open={deleting}
          onOpenChange={setDeleting}
          onDeleted={() => {
            unsaved.allowNextNavigation()
            void navigate({ to: '/teams/$team/runbooks', params: { team: team.slug }, replace: true })
          }}
        />
      )}
      {unsaved.dialog}
    </div>
  )
}
