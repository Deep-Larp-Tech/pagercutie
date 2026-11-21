// Placeholder overview; chunk 2 replaces it and moves Sign out into the user menu.
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useLogout } from '@/api/generated/auth/auth'
import { Button } from '@/components/ui/button'
import { unexpectedStatusMessage } from '@/lib/api'
import { useMe } from '@/lib/session'

export const Route = createFileRoute('/_app/')({
  component: HomePage,
})

function HomePage() {
  const { user } = useMe()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const logout = useLogout()
  const [error, setError] = useState<string | null>(null)

  async function signOut() {
    setError(null)
    const response = await logout.mutateAsync().catch(() => null)
    if (response === null) {
      setError("Couldn't reach PagerCutie. Check your connection and try again.")
      return
    }
    switch (response.status) {
      // 401: the session had already ended, which is what signing out wants.
      case 204:
      case 401:
        queryClient.clear()
        await navigate({ to: '/login' })
        return
      default:
        setError(unexpectedStatusMessage(response))
    }
  }

  return (
    <main className="mx-auto flex max-w-5xl flex-col items-start gap-3 p-8">
      <h1 className="text-[24px]/[32px] font-semibold tracking-[-0.02em]">PagerCutie</h1>
      <p>
        Signed in as {user.display_name} ({user.email})
      </p>
      <Button variant="secondary" disabled={logout.isPending} onClick={() => void signOut()}>
        Sign out
      </Button>
      {error !== null && (
        <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
          {error}
        </p>
      )}
    </main>
  )
}
