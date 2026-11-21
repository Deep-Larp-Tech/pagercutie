import { useMemo } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { createFileRoute, useRouter } from '@tanstack/react-router'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import type { HTTPValidationError, UserRead, UserUpdate } from '@/api/generated/model'
import { useUpdateUser } from '@/api/generated/users/users'
import { UpdateUserBody, updateUserBodyDisplayNameOneMax } from '@/api/generated/users/users.zod'
import { TimeZoneSelect } from '@/components/profile/time-zone-select'
import { PageHeader } from '@/components/shell/page-header'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { unexpectedStatusMessage } from '@/lib/api'
import { can } from '@/lib/permissions'
import { meQueryOptions, useMe } from '@/lib/session'

export const Route = createFileRoute('/_app/me/profile')({
  staticData: { title: 'Profile' },
  component: ProfilePage,
})

const fieldMessage = {
  display_name: `Enter a name of 1 to ${updateUserBodyDisplayNameOneMax} characters.`,
  phone: 'Enter the number in international format: a plus sign, the country code and the number, e.g. +420601234567.',
  timezone: 'Pick a time zone from the list.',
} as const satisfies Record<keyof ProfileValues, string>

const PHONE_REQUIRED = "You can't remove a phone number yet. Enter a different number instead."
const OFFLINE = "Couldn't reach PagerCutie. Check your connection and try again."

const displayName = UpdateUserBody.shape.display_name.unwrap().options[0]
const phone = UpdateUserBody.shape.phone.unwrap().options[0]
const timeZone = UpdateUserBody.shape.timezone.unwrap().options[0]

/**
 * Profile form values. An empty phone means "no number". `UserUpdate` has no way to clear a phone (`null` leaves it
 * unchanged), so a stored number cannot be emptied.
 */
function profileSchema(storedPhone: string | null) {
  return z
    .object({
      display_name: displayName,
      phone: z.union([z.literal(''), phone]),
      timezone: timeZone.min(1),
    })
    .superRefine((values, context) => {
      if (storedPhone !== null && values.phone === '') {
        context.addIssue({ code: 'custom', path: ['phone'], message: PHONE_REQUIRED })
      }
    })
}

type ProfileValues = z.infer<ReturnType<typeof profileSchema>>

const profileFields = ['display_name', 'phone', 'timezone'] as const satisfies readonly (keyof ProfileValues)[]

function toValues(user: UserRead): ProfileValues {
  return { display_name: user.display_name, phone: user.phone ?? '', timezone: user.timezone }
}

function ProfilePage() {
  const me = useMe()
  const router = useRouter()
  const queryClient = useQueryClient()
  const updateUser = useUpdateUser()
  const canEdit = can(me, 'profile.edit', me.user.id)
  const resolver = useMemo(
    () =>
      zodResolver(profileSchema(me.user.phone), {
        error: (issue) => {
          if (issue.code === 'custom') return undefined
          const field = profileFields.find((key) => key === issue.path?.[0])
          return field === undefined ? undefined : fieldMessage[field]
        },
      }),
    [me.user.phone],
  )
  const form = useForm<ProfileValues>({ resolver, defaultValues: toValues(me.user) })
  const { errors, isDirty, isSubmitting, dirtyFields } = form.formState

  const onSubmit = form.handleSubmit(async (values) => {
    const data: UserUpdate = {}
    if (dirtyFields.display_name === true) data.display_name = values.display_name
    if (dirtyFields.phone === true && values.phone !== '') data.phone = values.phone
    if (dirtyFields.timezone === true) data.timezone = values.timezone

    const response = await updateUser.mutateAsync({ userId: me.user.id, data }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 200:
        form.reset(toValues(response.data))
        toast.success('Profile saved')
        await queryClient.invalidateQueries({ queryKey: meQueryOptions.queryKey })
        await router.invalidate()
        return
      case 400:
        form.setError('root', { message: "Couldn't read the changes. Reload the page and try again." })
        return
      case 401:
        return
      case 403:
        form.setError('root', { message: "You can't change this profile. Only its owner or an admin can." })
        return
      case 404:
        form.setError('root', { message: "Your account doesn't exist anymore. Ask an admin to add you again." })
        return
      case 422:
        setValidationErrors(response.data)
        return
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  })

  /** Puts each FastAPI validation error under its field; anything else goes above the Save button. */
  function setValidationErrors(error: HTTPValidationError) {
    const others: string[] = []
    for (const { loc, msg } of error.detail ?? []) {
      const field = loc[0] === 'body' ? profileFields.find((key) => key === loc.at(-1)) : undefined
      if (field === undefined) others.push(msg)
      else form.setError(field, { message: fieldMessage[field] })
    }
    if (others.length > 0) form.setError('root', { message: `Couldn't save your profile. ${others.join(' ')}` })
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Profile" description="Your name, phone number and time zone." />
      <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex max-w-[480px] flex-col gap-6">
        <FieldGroup>
          <Field>
            <FieldLabel>Email</FieldLabel>
            <Input value={me.user.email} readOnly className="bg-muted text-muted-foreground" />
            <FieldDescription>Ask an admin to change your email.</FieldDescription>
          </Field>
          <Field invalid={errors.display_name !== undefined} disabled={!canEdit}>
            <FieldLabel>Display name</FieldLabel>
            <Input autoComplete="name" {...form.register('display_name')} />
            {errors.display_name?.message !== undefined && <FieldError>{errors.display_name.message}</FieldError>}
          </Field>
          <Field invalid={errors.phone !== undefined} disabled={!canEdit}>
            <FieldLabel>Phone</FieldLabel>
            <Input type="tel" autoComplete="tel" inputMode="tel" {...form.register('phone')} />
            <FieldDescription>Used for SMS and phone calls, e.g. +420601234567</FieldDescription>
            {errors.phone?.message !== undefined && <FieldError>{errors.phone.message}</FieldError>}
          </Field>
          <Field invalid={errors.timezone !== undefined} disabled={!canEdit}>
            <FieldLabel>Time zone</FieldLabel>
            <Controller
              control={form.control}
              name="timezone"
              render={({ field }) => (
                <TimeZoneSelect
                  value={field.value}
                  onValueChange={field.onChange}
                  onBlur={field.onBlur}
                  inputRef={field.ref}
                  disabled={!canEdit}
                />
              )}
            />
            <FieldDescription>Times in PagerCutie and your notification hours use this zone.</FieldDescription>
            {errors.timezone?.message !== undefined && <FieldError>{errors.timezone.message}</FieldError>}
          </Field>
        </FieldGroup>
        {errors.root?.message !== undefined && (
          <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
            {errors.root.message}
          </p>
        )}
        {canEdit && (
          <div>
            <Button type="submit" disabled={!isDirty || isSubmitting}>
              {isSubmitting ? 'Saving…' : 'Save profile'}
            </Button>
          </div>
        )}
      </form>
    </div>
  )
}
