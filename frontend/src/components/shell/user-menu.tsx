import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { ChevronDown, LogOut, UserRound } from 'lucide-react'
import { useLogout } from '@/api/generated/auth/auth'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { unexpectedStatusMessage } from '@/lib/api'
import { useMe } from '@/lib/session'

const OFFLINE = "Couldn't reach PagerCutie. Check your connection and try again."

/** Up to two initials from a display name, for the avatar. */
function initials(name: string): string {
  const letters = name
    .split(/\s+/)
    .filter((part) => part !== '')
    .map((part) => part[0]?.toUpperCase() ?? '')
  return (letters.length > 1 ? `${letters[0]}${letters.at(-1)}` : (letters[0] ?? '?')).slice(0, 2)
}

/** Account menu in the header: name and email, a link to the profile, and Sign out. */
export function UserMenu() {
  const { user } = useMe()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const logout = useLogout()
  const [error, setError] = useState<string | null>(null)

  async function signOut() {
    setError(null)
    const response = await logout.mutateAsync().catch(() => null)
    if (response === null) {
      setError(OFFLINE)
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
    <DropdownMenu onOpenChange={(open) => open && setError(null)}>
      <DropdownMenuTrigger
        render={<Button variant="ghost" className="gap-2 px-1.5 sm:pr-2" aria-label={`${user.display_name}, account menu`} />}
      >
        <span
          aria-hidden
          className="flex size-6 items-center justify-center rounded-full bg-muted text-[11px]/[16px] font-semibold text-foreground"
        >
          {initials(user.display_name)}
        </span>
        <span className="hidden max-w-40 truncate sm:inline">{user.display_name}</span>
        <ChevronDown strokeWidth={1.75} className="hidden text-muted-foreground sm:block" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuGroup>
          <div className="flex flex-col px-2 py-1.5">
            <span className="truncate font-medium">{user.display_name}</span>
            <span className="truncate text-[12px]/[16px] text-muted-foreground">{user.email}</span>
          </div>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem render={<Link to="/me/profile" />}>
          <UserRound strokeWidth={1.75} />
          Profile
        </DropdownMenuItem>
        <DropdownMenuItem closeOnClick={false} disabled={logout.isPending} onClick={() => void signOut()}>
          <LogOut strokeWidth={1.75} />
          Sign out
        </DropdownMenuItem>
        {error !== null && (
          <p role="alert" className="px-2 pt-1 pb-1.5 text-[12px]/[16px] font-medium text-alert-red-text">
            {error}
          </p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
