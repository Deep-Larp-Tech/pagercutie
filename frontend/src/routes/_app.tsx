import { createFileRoute, redirect, useRouter, type ErrorComponentProps } from '@tanstack/react-router'
import { AppShell } from '@/components/shell/app-shell'
import { Button } from '@/components/ui/button'
import { UnexpectedStatusError, unexpectedStatusMessage } from '@/lib/api'
import { meQueryOptions } from '@/lib/session'

/**
 * Pathless layout for every signed-in screen: loads `GET /me` into the route context or sends the user to sign in, then
 * renders the shell. `SessionError` covers a failing `GET /me` only; screens fail inside the shell (`AppShell`).
 */
export const Route = createFileRoute('/_app')({
  beforeLoad: async ({ context, location }) => {
    const response = await context.queryClient.fetchQuery(meQueryOptions)
    switch (response.status) {
      case 200:
        return { me: response.data }
      case 401:
        throw redirect({ to: '/login', search: { redirect: location.href } })
      default:
        throw new UnexpectedStatusError(unexpectedStatusMessage(response))
    }
  },
  component: AppShell,
  errorComponent: SessionError,
})

function SessionError({ error }: ErrorComponentProps) {
  const router = useRouter()
  const detail =
    error instanceof UnexpectedStatusError ? error.message : 'Check your connection and try again.'
  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <div className="flex max-w-[360px] flex-col items-start gap-3">
        <div role="alert" className="flex flex-col gap-1">
          <h1 className="text-[18px]/[26px] font-semibold tracking-[-0.01em]">
            Couldn't load your account
          </h1>
          <p className="text-muted-foreground">{detail}</p>
        </div>
        <Button variant="secondary" onClick={() => void router.invalidate()}>
          Try again
        </Button>
      </div>
    </main>
  )
}
