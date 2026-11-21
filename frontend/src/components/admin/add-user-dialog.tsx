import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import type { z } from 'zod'
import { getListUsersQueryKey, useCreateUser } from '@/api/generated/users/users'
import { CreateUserBody, createUserBodyRoleDefault } from '@/api/generated/users/users.zod'
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
import { browserTimeZone } from '@/lib/time-zones'
import { FormError } from './list-parts'
import { PHONE_HELP, PHONE_INVALID, TIME_ZONE_HELP } from './copy'
import { GlobalRoleSelect, TimeZoneSelect } from './user-fields'

type Values = z.input<typeof CreateUserBody>

const FIELDS = ['email', 'display_name', 'phone', 'timezone', 'role'] as const satisfies readonly (keyof Values)[]

const resolver = zodResolver(CreateUserBody, {
  error: (issue) => {
    const empty = issue.input === '' || issue.input === undefined
    switch (issue.path?.[0]) {
      case 'email':
        return empty ? 'Enter an email address.' : 'Enter a valid email address.'
      case 'display_name':
        return empty ? 'Enter a name.' : 'Use at most 100 characters.'
      case 'phone':
        return PHONE_INVALID
      default:
        return undefined
    }
  },
})

/** **Add user** button and the dialog that creates a user (`POST /users`, admin only). */
export function AddUserDialog() {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>Add user</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add user</DialogTitle>
          <DialogDescription>They sign in with this email. Add them to teams from each team's settings.</DialogDescription>
        </DialogHeader>
        <AddUserForm onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  )
}

function AddUserForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient()
  const createUser = useCreateUser()
  const form = useForm<Values, unknown, z.output<typeof CreateUserBody>>({
    resolver,
    defaultValues: {
      email: '',
      display_name: '',
      phone: null,
      timezone: browserTimeZone(),
      role: createUserBodyRoleDefault,
    },
  })
  const { errors, isSubmitting } = form.formState

  const onSubmit = form.handleSubmit(async (values) => {
    const response = await createUser.mutateAsync({ data: values }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 201:
        await queryClient.invalidateQueries({ queryKey: getListUsersQueryKey() })
        toast.success(`${response.data.display_name} added`)
        onDone()
        return
      case 409:
        form.setError('email', { message: 'A user with this email already exists. Use another email.' })
        return
      case 422:
        applyValidationErrors(form.setError, response.data, FIELDS)
        return
      case 400:
        form.setError('root', { message: "Couldn't read the form. Reload the page and try again." })
        return
      case 403:
        form.setError('root', { message: 'Only admins can add users.' })
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
        <Field invalid={errors.email !== undefined}>
          <FieldLabel>Email</FieldLabel>
          <Input type="email" autoComplete="off" autoFocus {...form.register('email')} />
          {errors.email?.message !== undefined && <FieldError>{errors.email.message}</FieldError>}
        </Field>
        <Field invalid={errors.display_name !== undefined}>
          <FieldLabel>Name</FieldLabel>
          <Input autoComplete="off" {...form.register('display_name')} />
          {errors.display_name?.message !== undefined && <FieldError>{errors.display_name.message}</FieldError>}
        </Field>
        <Field invalid={errors.phone !== undefined}>
          <FieldLabel>Phone</FieldLabel>
          <Input
            type="tel"
            autoComplete="off"
            {...form.register('phone', { setValueAs: (value: string | null) => (value === '' ? null : value) })}
          />
          <FieldDescription>{PHONE_HELP}</FieldDescription>
          {errors.phone?.message !== undefined && <FieldError>{errors.phone.message}</FieldError>}
        </Field>
        <Field invalid={errors.timezone !== undefined}>
          <FieldLabel>Time zone</FieldLabel>
          <Controller
            control={form.control}
            name="timezone"
            render={({ field }) => <TimeZoneSelect value={field.value ?? browserTimeZone()} onChange={field.onChange} />}
          />
          <FieldDescription>{TIME_ZONE_HELP}</FieldDescription>
          {errors.timezone?.message !== undefined && <FieldError>{errors.timezone.message}</FieldError>}
        </Field>
        <Field invalid={errors.role !== undefined}>
          <FieldLabel>Global role</FieldLabel>
          <Controller
            control={form.control}
            name="role"
            render={({ field }) => (
              <GlobalRoleSelect value={field.value ?? createUserBodyRoleDefault} onChange={field.onChange} />
            )}
          />
          <FieldDescription>Admins manage every user and team.</FieldDescription>
          {errors.role?.message !== undefined && <FieldError>{errors.role.message}</FieldError>}
        </Field>
      </FieldGroup>
      {errors.root?.message !== undefined && <FormError>{errors.root.message}</FormError>}
      <DialogFooter>
        <DialogClose render={<Button variant="secondary" />}>Cancel</DialogClose>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Adding…' : 'Add user'}
        </Button>
      </DialogFooter>
    </form>
  )
}
