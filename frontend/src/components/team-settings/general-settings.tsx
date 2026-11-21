import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import type { TeamRead, TeamUpdate } from '@/api/generated/model'
import {
  getGetTeamQueryKey,
  getGetTeamQueryOptions,
  useUpdateTeam,
} from '@/api/generated/teams/teams'
import { updateTeamBodyDescriptionOneMax, updateTeamBodyNameOneMax } from '@/api/generated/teams/teams.zod'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { unexpectedStatusMessage } from '@/lib/api'
import { meQueryOptions } from '@/lib/session'
import { adminTeamsQueryOptions } from '@/lib/teams'
import { bodyIssues } from '@/lib/validation-errors'
import { LOAD_REJECTED, OFFLINE, SAVE_FORBIDDEN, SAVE_REJECTED, TEAM_GONE } from './messages'
import { FormError, Section, SectionError, SectionSkeleton } from './section'
import { useTeamSettings } from './use-team-settings'

const generalSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, 'Enter a team name.')
    .max(updateTeamBodyNameOneMax, `Use at most ${updateTeamBodyNameOneMax} characters.`),
  description: z
    .string()
    .trim()
    .max(updateTeamBodyDescriptionOneMax, `Use at most ${updateTeamBodyDescriptionOneMax} characters.`),
})

type GeneralForm = z.infer<typeof generalSchema>

/** `/teams/$team/settings/general`: the team's name and description (`GET`/`PATCH /teams/{id}`). */
export function GeneralSettings() {
  const { team, canEdit } = useTeamSettings()
  const query = useQuery(getGetTeamQueryOptions(team.id))

  let body
  if (query.isPending) body = <SectionSkeleton rows={2} />
  else if (query.isError) body = <SectionError message={OFFLINE} onRetry={() => void query.refetch()} />
  else {
    const response = query.data
    switch (response.status) {
      case 200:
        body = canEdit ? <GeneralFormView team={response.data} /> : <GeneralReadOnly team={response.data} />
        break
      case 401:
        body = null
        break
      case 404:
        body = <SectionError message={TEAM_GONE} />
        break
      case 422:
        body = <SectionError message={LOAD_REJECTED} />
        break
      default:
        body = <SectionError message={unexpectedStatusMessage(response)} onRetry={() => void query.refetch()} />
    }
  }

  return (
    <Section title="General" description="The name everyone sees in the team switcher and on alerts.">
      {body}
    </Section>
  )
}

function GeneralReadOnly({ team }: { team: TeamRead }) {
  return (
    <dl className="grid max-w-[480px] grid-cols-[120px_1fr] gap-x-4 gap-y-3">
      <dt className="text-muted-foreground">Name</dt>
      <dd>{team.name}</dd>
      <dt className="text-muted-foreground">Description</dt>
      <dd>{team.description ?? <span className="text-muted-foreground">No description</span>}</dd>
    </dl>
  )
}

function GeneralFormView({ team }: { team: TeamRead }) {
  const queryClient = useQueryClient()
  const router = useRouter()
  const update = useUpdateTeam()
  const form = useForm<GeneralForm>({
    resolver: zodResolver(generalSchema),
    defaultValues: { name: team.name, description: team.description ?? '' },
  })
  const { errors, isSubmitting } = form.formState

  const onSubmit = form.handleSubmit(async ({ name, description }) => {
    if (description === '' && team.description !== null) {
      form.setError('description', {
        message: "A description can't be removed yet. Enter a new one instead.",
      })
      return
    }
    const data: TeamUpdate = description === '' ? { name } : { name, description }
    const response = await update.mutateAsync({ teamId: team.id, data }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 200:
        form.reset({ name: response.data.name, description: response.data.description ?? '' })
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: getGetTeamQueryKey(team.id) }),
          queryClient.invalidateQueries({ queryKey: meQueryOptions.queryKey }),
          queryClient.invalidateQueries({ queryKey: adminTeamsQueryOptions.queryKey }),
        ])
        await router.invalidate()
        toast.success('Team settings saved')
        return
      case 400:
        form.setError('root', { message: SAVE_REJECTED })
        return
      case 401:
        return
      case 403:
        form.setError('root', { message: SAVE_FORBIDDEN })
        return
      case 404:
        form.setError('root', { message: TEAM_GONE })
        return
      case 422: {
        const issues = bodyIssues(response.data)
        for (const { path, message } of issues) {
          const field = path[0]
          if (field === 'name' || field === 'description') form.setError(field, { message })
          else form.setError('root', { message })
        }
        if (issues.length === 0) form.setError('root', { message: SAVE_REJECTED })
        return
      }
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  })

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex max-w-[480px] flex-col gap-4">
      <FieldGroup>
        <Field invalid={errors.name !== undefined}>
          <FieldLabel>Name</FieldLabel>
          <Input autoComplete="off" {...form.register('name')} />
          {errors.name?.message !== undefined && <FieldError>{errors.name.message}</FieldError>}
        </Field>
        <Field invalid={errors.description !== undefined}>
          <FieldLabel>Description</FieldLabel>
          <Input autoComplete="off" {...form.register('description')} />
          <FieldDescription>One line about what the team looks after.</FieldDescription>
          {errors.description?.message !== undefined && <FieldError>{errors.description.message}</FieldError>}
        </Field>
      </FieldGroup>
      {errors.root?.message !== undefined && <FormError>{errors.root.message}</FormError>}
      <div>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Saving…' : 'Save changes'}
        </Button>
      </div>
    </form>
  )
}
