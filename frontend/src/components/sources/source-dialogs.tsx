import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import type { SourceRead, TeamRead } from '@/api/generated/model'
import {
  getGetSourceQueryKey,
  getGetSourceQueryOptions,
  getListSourcesQueryKey,
  useCreateSource,
  useUpdateSource,
} from '@/api/generated/sources/sources'
import { FormError } from '@/components/team-settings/section'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { unexpectedStatusMessage } from '@/lib/api'
import { sourceTypeLabel } from '@/lib/ingest-example'
import { OFFLINE } from '@/lib/pagination'
import { bodyIssues, type BodyIssue } from '@/lib/validation-errors'
import { SourceFields, type SourceForm } from './source-fields'
import {
  fromSource,
  NEW_SOURCE,
  sourceFormSchema,
  sourceIssueField,
  toCreate,
  toUpdate,
  type SourceFormOutput,
  type SourceFormValues,
} from './source-form'
import { FirstTokenStep } from './token-dialogs'

/** The dialog is tall (severity mapping), so it scrolls inside the viewport. */
const DIALOG_CLASS = 'max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl'

/** A save answered `400` or a `422` without field errors. */
const SAVE_REJECTED = "Couldn't save the source. Reload the page and try again."

/** A source answered `404` while editing. */
const SOURCE_GONE = 'This source no longer exists. Close this dialog to see the current list.'

function useSourceForm(defaultValues: SourceFormValues): SourceForm {
  return useForm<SourceFormValues, unknown, SourceFormOutput>({ resolver: zodResolver(sourceFormSchema), defaultValues })
}

function applyIssues(form: SourceForm, issues: readonly BodyIssue[]) {
  if (issues.length === 0) form.setError('root', { message: SAVE_REJECTED })
  for (const { path, message } of issues) form.setError(sourceIssueField(path), { message })
}

/** **New source** button and the dialog that creates a source (`POST /sources`), then offers its first token. */
export function AddSourceDialog({ team }: { team: TeamRead }) {
  const [open, setOpen] = useState(false)
  const [created, setCreated] = useState<SourceRead | null>(null)

  function onOpenChange(next: boolean) {
    setOpen(next)
    if (!next) setCreated(null)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger render={<Button />}>New source</DialogTrigger>
      <DialogContent className={DIALOG_CLASS}>
        {created === null ? (
          <>
            <DialogHeader>
              <DialogTitle>New source</DialogTitle>
              <DialogDescription>A system that sends events to {team.name}.</DialogDescription>
            </DialogHeader>
            <AddSourceForm team={team} onCreated={setCreated} />
          </>
        ) : (
          <FirstTokenStep source={created} title={`${created.name} added`} onDone={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  )
}

function AddSourceForm({ team, onCreated }: { team: TeamRead; onCreated: (source: SourceRead) => void }) {
  const queryClient = useQueryClient()
  const create = useCreateSource()
  const form = useSourceForm(NEW_SOURCE)
  const { errors, isSubmitting } = form.formState

  const onSubmit = form.handleSubmit(async (values) => {
    const response = await create.mutateAsync({ data: toCreate(values, team.id) }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 201:
        await queryClient.invalidateQueries({ queryKey: getListSourcesQueryKey() })
        onCreated(response.data)
        return
      case 409:
        form.setError('slug', { message: 'Another source already uses this slug. Pick another one.' })
        return
      case 422:
        applyIssues(form, bodyIssues(response.data))
        return
      case 400:
        form.setError('root', { message: SAVE_REJECTED })
        return
      case 403:
        form.setError('root', { message: 'Only members and leads can add sources.' })
        return
      case 404:
        form.setError('root', { message: 'The team no longer exists. Reload the page and try again.' })
        return
      case 401:
        return
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  })

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-5">
      <SourceFields form={form} create teamSlug={team.slug} />
      {errors.root?.message !== undefined && <FormError>{errors.root.message}</FormError>}
      <DialogFooter>
        <DialogClose render={<Button variant="secondary" />}>Cancel</DialogClose>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Adding…' : 'Add source'}
        </Button>
      </DialogFooter>
    </form>
  )
}

/** Props for `EditSourceDialog`. */
export interface EditSourceDialogProps {
  /** The source to edit, as listed; `null` closes the dialog. The form loads it again with `GET /sources/{id}`. */
  source: SourceRead | null
  team: TeamRead
  onClose: () => void
}

/** Dialog that changes a source (`GET`, then `PATCH /sources/{id}`); slug and type are permanent. */
export function EditSourceDialog({ source, team, onClose }: EditSourceDialogProps) {
  return (
    <Dialog open={source !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className={DIALOG_CLASS}>
        <DialogHeader>
          <DialogTitle>Edit source</DialogTitle>
          {source !== null && (
            <DialogDescription>
              <span className="font-mono text-[13px]/[20px]">{source.slug}</span> · {sourceTypeLabel[source.type]}
            </DialogDescription>
          )}
        </DialogHeader>
        {source !== null && <EditSourceBody sourceId={source.id} team={team} onDone={onClose} />}
      </DialogContent>
    </Dialog>
  )
}

function EditSourceBody({ sourceId, team, onDone }: { sourceId: string; team: TeamRead; onDone: () => void }) {
  const query = useQuery(getGetSourceQueryOptions(sourceId))
  if (query.isPending) {
    return (
      <div className="flex flex-col gap-3" data-testid="source-skeleton">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-8 w-full" />
        ))}
      </div>
    )
  }
  if (query.isError) return <FormError>{OFFLINE}</FormError>
  const response = query.data
  switch (response.status) {
    case 200:
      return <EditSourceForm source={response.data} team={team} onDone={onDone} />
    case 404:
      return <FormError>{SOURCE_GONE}</FormError>
    case 422:
      return <FormError>Couldn't load this source. Reload the page and try again.</FormError>
    case 401:
      return null
    default:
      return <FormError>{unexpectedStatusMessage(response)}</FormError>
  }
}

function EditSourceForm({ source, team, onDone }: { source: SourceRead; team: TeamRead; onDone: () => void }) {
  const queryClient = useQueryClient()
  const update = useUpdateSource()
  const form = useSourceForm(fromSource(source))
  const { errors, isSubmitting, isDirty } = form.formState

  const onSubmit = form.handleSubmit(async (values) => {
    const data = toUpdate(values, source)
    if (Object.keys(data).length === 0) {
      onDone()
      return
    }
    const response = await update.mutateAsync({ sourceId: source.id, data }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 200:
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: getListSourcesQueryKey() }),
          queryClient.invalidateQueries({ queryKey: getGetSourceQueryKey(source.id) }),
        ])
        toast.success(`${response.data.name} saved`)
        onDone()
        return
      case 422:
        applyIssues(form, bodyIssues(response.data))
        return
      case 400:
        form.setError('root', { message: SAVE_REJECTED })
        return
      case 403:
        form.setError('root', { message: 'Only members and leads can change sources.' })
        return
      case 404:
        form.setError('root', { message: SOURCE_GONE })
        return
      case 401:
        return
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  })

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-5">
      <SourceFields form={form} create={false} teamSlug={team.slug} />
      {errors.root?.message !== undefined && <FormError>{errors.root.message}</FormError>}
      <DialogFooter>
        <DialogClose render={<Button variant="secondary" />}>Cancel</DialogClose>
        <Button type="submit" disabled={isSubmitting || !isDirty}>
          {isSubmitting ? 'Saving…' : 'Save changes'}
        </Button>
      </DialogFooter>
    </form>
  )
}
