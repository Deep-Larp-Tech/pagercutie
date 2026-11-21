import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import type { z } from 'zod'
import type { TeamRead, TeamUpdate } from '@/api/generated/model'
import { getListTeamsQueryKey, useUpdateTeam } from '@/api/generated/teams/teams'
import { UpdateTeamBody } from '@/api/generated/teams/teams.zod'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { unexpectedStatusMessage } from '@/lib/api'
import { applyValidationErrors } from '@/lib/form-errors'
import { OFFLINE } from '@/lib/pagination'
import { meQueryOptions } from '@/lib/session'
import { FormError } from './list-parts'

type Values = z.input<typeof UpdateTeamBody>

const FIELDS = ['name', 'description'] as const satisfies readonly (keyof Values)[]

const resolver = zodResolver(UpdateTeamBody, {
  error: (issue) => {
    switch (issue.path?.[0]) {
      case 'name':
        return issue.input === '' ? 'Enter a team name.' : 'Use at most 100 characters.'
      case 'description':
        return 'Use at most 2,000 characters.'
      default:
        return undefined
    }
  },
})

/** Props for `EditTeamDialog`. */
export interface EditTeamDialogProps {
  /** The team being edited; `null` closes the dialog. */
  team: TeamRead | null
  onClose: () => void
}

/** Dialog that changes a team's name and description (`PATCH /teams/{id}`); the slug is permanent. */
export function EditTeamDialog({ team, onClose }: EditTeamDialogProps) {
  return (
    <Dialog open={team !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit team</DialogTitle>
          <DialogDescription className="font-mono text-[13px]/[20px]">{team?.slug}</DialogDescription>
        </DialogHeader>
        {team !== null && <EditTeamForm team={team} onDone={onClose} />}
      </DialogContent>
    </Dialog>
  )
}

function EditTeamForm({ team, onDone }: { team: TeamRead; onDone: () => void }) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const updateTeam = useUpdateTeam()
  const form = useForm<Values, unknown, z.output<typeof UpdateTeamBody>>({
    resolver,
    defaultValues: { name: team.name, description: team.description },
  })
  const { errors, isSubmitting, dirtyFields } = form.formState

  const onSubmit = form.handleSubmit(async (values) => {
    // PATCH treats null as "unchanged" (TeamUpdate), so an emptied description would be ignored without a word.
    if (values.description === null && team.description !== null) {
      form.setError('description', { message: "A description can't be removed yet. Enter another one instead." })
      return
    }
    const data: TeamUpdate = {}
    if (dirtyFields.name === true) data.name = values.name
    if (dirtyFields.description === true) data.description = values.description
    if (Object.keys(data).length === 0) {
      onDone()
      return
    }
    const response = await updateTeam.mutateAsync({ teamId: team.id, data }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 200:
        // Memberships in `GET /me` carry the team's name, which the sidebar and team layout show.
        await queryClient.invalidateQueries({ queryKey: getListTeamsQueryKey() })
        await queryClient.invalidateQueries(meQueryOptions)
        await router.invalidate()
        toast.success(`Changes to ${response.data.name} saved`)
        onDone()
        return
      case 422:
        applyValidationErrors(form.setError, response.data, FIELDS)
        return
      case 400:
        form.setError('root', { message: "Couldn't read the form. Reload the page and try again." })
        return
      case 403:
        form.setError('root', { message: 'Only admins and team leads can change this team.' })
        return
      case 404:
        await queryClient.invalidateQueries({ queryKey: getListTeamsQueryKey() })
        form.setError('root', { message: 'This team no longer exists. Close this dialog to see the current list.' })
        return
      case 401:
        // The sign-in redirect is under way (ADR-0052).
        return
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  })

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-5">
      <FieldGroup>
        <Field invalid={errors.name !== undefined}>
          <FieldLabel>Name</FieldLabel>
          <Input autoComplete="off" autoFocus {...form.register('name')} />
          {errors.name?.message !== undefined && <FieldError>{errors.name.message}</FieldError>}
        </Field>
        <Field invalid={errors.description !== undefined}>
          <FieldLabel>Description</FieldLabel>
          <Input
            autoComplete="off"
            {...form.register('description', { setValueAs: (value: string | null) => (value === '' ? null : value) })}
          />
          <FieldDescription>Optional. What the team looks after, in one line.</FieldDescription>
          {errors.description?.message !== undefined && <FieldError>{errors.description.message}</FieldError>}
        </Field>
      </FieldGroup>
      {errors.root?.message !== undefined && <FormError>{errors.root.message}</FormError>}
      <DialogFooter>
        <DialogClose render={<Button variant="secondary" />}>Cancel</DialogClose>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Saving…' : 'Save changes'}
        </Button>
      </DialogFooter>
    </form>
  )
}
