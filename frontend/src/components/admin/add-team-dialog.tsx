import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import type { z } from 'zod'
import { getListTeamsQueryKey, useCreateTeam } from '@/api/generated/teams/teams'
import { CreateTeamBody } from '@/api/generated/teams/teams.zod'
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
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { unexpectedStatusMessage } from '@/lib/api'
import { applyValidationErrors } from '@/lib/form-errors'
import { OFFLINE } from '@/lib/pagination'
import { slugify } from '@/lib/slug'
import { FormError } from './list-parts'

type Values = z.input<typeof CreateTeamBody>

const FIELDS = ['name', 'slug', 'description'] as const satisfies readonly (keyof Values)[]

/** Shown when a slug does not match the slug pattern (DOMAIN.md §1). */
const SLUG_INVALID = 'Use lower case letters and digits, joined by single hyphens, at most 50 characters.'

const resolver = zodResolver(CreateTeamBody, {
  error: (issue) => {
    switch (issue.path?.[0]) {
      case 'name':
        return issue.input === '' ? 'Enter a team name.' : 'Use at most 100 characters.'
      case 'slug':
        return issue.input === '' ? 'Enter a slug.' : SLUG_INVALID
      case 'description':
        return 'Use at most 2,000 characters.'
      default:
        return undefined
    }
  },
})

/** **Add team** button and the dialog that creates a team (`POST /teams`, admin only). */
export function AddTeamDialog() {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>Add team</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add team</DialogTitle>
          <DialogDescription>Add members and a rotation from the team's settings afterwards.</DialogDescription>
        </DialogHeader>
        <AddTeamForm onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  )
}

function AddTeamForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient()
  const createTeam = useCreateTeam()
  const form = useForm<Values, unknown, z.output<typeof CreateTeamBody>>({
    resolver,
    defaultValues: { name: '', slug: '', description: null },
  })
  const { errors, isSubmitting } = form.formState
  const [slugEdited, setSlugEdited] = useState(false)
  const nameField = form.register('name', {
    onChange: (event: { target: { value: string } }) => {
      if (!slugEdited) form.setValue('slug', slugify(event.target.value))
    },
  })
  const slugField = form.register('slug', { onChange: () => setSlugEdited(true) })

  const onSubmit = form.handleSubmit(async (values) => {
    const response = await createTeam.mutateAsync({ data: values }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 201:
        await queryClient.invalidateQueries({ queryKey: getListTeamsQueryKey() })
        toast.success(`${response.data.name} added`)
        onDone()
        return
      case 409:
        form.setError('slug', { message: 'Another team already uses this slug. Pick another one.' })
        return
      case 422:
        applyValidationErrors(form.setError, response.data, FIELDS)
        return
      case 400:
        form.setError('root', { message: "Couldn't read the form. Reload the page and try again." })
        return
      case 403:
        form.setError('root', { message: 'Only admins can add teams.' })
        return
      case 401:
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
          <Input autoComplete="off" autoFocus {...nameField} />
          {errors.name?.message !== undefined && <FieldError>{errors.name.message}</FieldError>}
        </Field>
        <Field invalid={errors.slug !== undefined}>
          <FieldLabel>Slug</FieldLabel>
          <Input autoComplete="off" spellCheck={false} className="font-mono text-[13px]" {...slugField} />
          <FieldDescription>Used in links, e.g. /teams/payments/alerts. It can't be changed later.</FieldDescription>
          {errors.slug?.message !== undefined && <FieldError>{errors.slug.message}</FieldError>}
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
          {isSubmitting ? 'Adding…' : 'Add team'}
        </Button>
      </DialogFooter>
    </form>
  )
}
