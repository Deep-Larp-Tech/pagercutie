import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import type { z } from 'zod'
import type { UserRead, UserUpdate } from '@/api/generated/model'
import { getGetUserQueryOptions, getListUsersQueryKey, useUpdateUser } from '@/api/generated/users/users'
import { UpdateUserBody } from '@/api/generated/users/users.zod'
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
import { Skeleton } from '@/components/ui/skeleton'
import { unexpectedStatusMessage } from '@/lib/api'
import { applyValidationErrors } from '@/lib/form-errors'
import { OFFLINE } from '@/lib/pagination'
import { meQueryOptions, useMe } from '@/lib/session'
import { FormError } from './list-parts'
import { PHONE_HELP, PHONE_INVALID, TIME_ZONE_HELP } from './copy'
import { GlobalRoleSelect, TimeZoneSelect } from './user-fields'

type Values = z.input<typeof UpdateUserBody>

const FIELDS = ['display_name', 'phone', 'timezone', 'role'] as const satisfies readonly (keyof Values)[]

const resolver = zodResolver(UpdateUserBody, {
  error: (issue) => {
    switch (issue.path?.[0]) {
      case 'display_name':
        return issue.input === '' ? 'Enter a name.' : 'Use at most 100 characters.'
      case 'phone':
        return PHONE_INVALID
      default:
        return undefined
    }
  },
})

/** Props for `EditUserDialog`. */
export interface EditUserDialogProps {
  /** The user being edited; `null` closes the dialog. */
  user: UserRead | null
  onClose: () => void
}

/**
 * Dialog that changes a user's name, phone, time zone and global role (`PATCH /users/{id}`). The form starts from
 * `GET /users/{id}`, so it shows the stored values even when the list is stale.
 */
export function EditUserDialog({ user, onClose }: EditUserDialogProps) {
  return (
    <Dialog open={user !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit user</DialogTitle>
          <DialogDescription>{user?.email}</DialogDescription>
        </DialogHeader>
        {user !== null && <CurrentUser userId={user.id} onDone={onClose} />}
      </DialogContent>
    </Dialog>
  )
}

/** Loads the user with `GET /users/{id}`, then shows the form. */
function CurrentUser({ userId, onDone }: { userId: string; onDone: () => void }) {
  const { data: response, isError } = useQuery(getGetUserQueryOptions(userId, { query: { staleTime: 0 } }))
  if (isError) return <FormError>{OFFLINE}</FormError>
  if (response === undefined) {
    return (
      <div aria-busy className="flex flex-col gap-4">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="flex flex-col gap-1.5">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-8 w-full" />
          </div>
        ))}
      </div>
    )
  }
  switch (response.status) {
    case 200:
      return <EditUserForm user={response.data} onDone={onDone} />
    case 404:
      return <FormError>This user no longer exists. Close this dialog to see the current list.</FormError>
    case 422:
      return <FormError>Couldn't load this user. Reload the page and try again.</FormError>
    case 401:
      // The sign-in redirect is under way (ADR-0048).
      return null
    default:
      return <FormError>{unexpectedStatusMessage(response)}</FormError>
  }
}

function EditUserForm({ user, onDone }: { user: UserRead; onDone: () => void }) {
  const me = useMe()
  const router = useRouter()
  const queryClient = useQueryClient()
  const updateUser = useUpdateUser()
  const form = useForm<Values, unknown, z.output<typeof UpdateUserBody>>({
    resolver,
    defaultValues: {
      display_name: user.display_name,
      phone: user.phone,
      timezone: user.timezone,
      role: user.role,
    },
  })
  const { errors, isSubmitting, dirtyFields } = form.formState

  const onSubmit = form.handleSubmit(async (values) => {
    // PATCH treats null as "unchanged" (UserUpdate), so an emptied phone would be ignored without a word.
    if (values.phone === null && user.phone !== null) {
      form.setError('phone', { message: "A phone number can't be removed yet. Enter another number instead." })
      return
    }
    const data: UserUpdate = {}
    if (dirtyFields.display_name === true) data.display_name = values.display_name
    if (dirtyFields.phone === true) data.phone = values.phone
    if (dirtyFields.timezone === true) data.timezone = values.timezone
    if (dirtyFields.role === true) data.role = values.role
    if (Object.keys(data).length === 0) {
      onDone()
      return
    }
    const response = await updateUser.mutateAsync({ userId: user.id, data }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 200:
        await queryClient.invalidateQueries({ queryKey: getListUsersQueryKey() })
        if (user.id === me.user.id) {
          await queryClient.invalidateQueries(meQueryOptions)
          await router.invalidate()
        }
        toast.success(`Changes to ${response.data.display_name} saved`)
        onDone()
        return
      case 422:
        applyValidationErrors(form.setError, response.data, FIELDS)
        return
      case 400:
        form.setError('root', { message: "Couldn't read the form. Reload the page and try again." })
        return
      case 403:
        form.setError('root', { message: 'Only admins can change other users.' })
        return
      case 404:
        await queryClient.invalidateQueries({ queryKey: getListUsersQueryKey() })
        form.setError('root', { message: 'This user no longer exists. Close this dialog to see the current list.' })
        return
      case 401:
        // The sign-in redirect is under way (ADR-0048).
        return
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  })

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-5">
      <FieldGroup>
        <Field invalid={errors.display_name !== undefined}>
          <FieldLabel>Name</FieldLabel>
          <Input autoComplete="off" autoFocus {...form.register('display_name')} />
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
            render={({ field }) => <TimeZoneSelect value={field.value ?? user.timezone} onChange={field.onChange} />}
          />
          <FieldDescription>{TIME_ZONE_HELP}</FieldDescription>
          {errors.timezone?.message !== undefined && <FieldError>{errors.timezone.message}</FieldError>}
        </Field>
        <Field invalid={errors.role !== undefined}>
          <FieldLabel>Global role</FieldLabel>
          <Controller
            control={form.control}
            name="role"
            render={({ field }) => <GlobalRoleSelect value={field.value ?? user.role} onChange={field.onChange} />}
          />
          <FieldDescription>Admins manage every user and team.</FieldDescription>
          {errors.role?.message !== undefined && <FieldError>{errors.role.message}</FieldError>}
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
