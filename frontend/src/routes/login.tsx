import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { createFileRoute, redirect, useNavigate } from '@tanstack/react-router'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { useLogin } from '@/api/generated/auth/auth'
import { LoginBody } from '@/api/generated/auth/auth.zod'
import type { HTTPValidationError, LoginRequest } from '@/api/generated/model'
import { Logo } from '@/components/brand/Logo'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { unexpectedStatusMessage } from '@/lib/api'
import { meQueryOptions, safeRedirect } from '@/lib/session'

const loginSearch = z.object({
  /** Path to open after sign in; anything that is not a path on this origin falls back to `/`. */
  redirect: z.string().optional(),
})

export const Route = createFileRoute('/login')({
  validateSearch: loginSearch,
  beforeLoad: async ({ context }) => {
    const response = await context.queryClient.fetchQuery(meQueryOptions)
    if (response.status === 200) throw redirect({ to: '/' })
  },
  component: LoginPage,
})

const INVALID_EMAIL = 'Enter a valid email address.'
const UNKNOWN_EMAIL = 'No account with that email. Ask an admin to add you.'
const OFFLINE = "Couldn't reach PagerCutie. Check your connection and try again."

const resolver = zodResolver(LoginBody, {
  error: (issue) => (issue.input === '' ? 'Enter your work email.' : INVALID_EMAIL),
})

/** The `msg` FastAPI reports for `field` in the request body, if any. */
function bodyFieldError(error: HTTPValidationError, field: keyof LoginRequest): string | undefined {
  return error.detail?.find(({ loc }) => loc[0] === 'body' && loc.at(-1) === field)?.msg
}

function LoginPage() {
  const search = Route.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const login = useLogin()
  const form = useForm<LoginRequest>({ resolver, defaultValues: { email: '' } })
  const { errors, isSubmitting } = form.formState

  const onSubmit = form.handleSubmit(async (values) => {
    const response = await login.mutateAsync({ data: values }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 200:
        // Drops data cached for whoever was signed in before; seeding `me` saves the layout a refetch.
        queryClient.removeQueries()
        queryClient.setQueryData(meQueryOptions.queryKey, response)
        await navigate({ href: safeRedirect(search.redirect), replace: true })
        return
      case 404:
        form.setError('email', { message: UNKNOWN_EMAIL })
        return
      case 400:
        form.setError('email', { message: INVALID_EMAIL })
        return
      case 422:
        form.setError('email', { message: bodyFieldError(response.data, 'email') ?? INVALID_EMAIL })
        return
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  })

  return (
    <main className="flex min-h-svh items-center justify-center bg-background p-4">
      <div className="flex w-full max-w-[360px] flex-col gap-6 rounded-lg border bg-card p-6 text-card-foreground shadow-card">
        <div className="flex flex-col gap-1">
          <h1 className="mb-2">
            <Logo height={32} />
          </h1>
          <p className="text-muted-foreground">Alerts for your team, on the channel each person prefers.</p>
        </div>
        <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-4">
          <Field invalid={errors.email !== undefined}>
            <FieldLabel>Work email</FieldLabel>
            <Input type="email" autoComplete="email" autoFocus {...form.register('email')} />
            {errors.email?.message !== undefined && <FieldError>{errors.email.message}</FieldError>}
          </Field>
          {errors.root?.message !== undefined && (
            <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
              {errors.root.message}
            </p>
          )}
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
      </div>
    </main>
  )
}
