import { useQuery } from '@tanstack/react-query'
import type { UserRead } from '@/api/generated/model'
import { getListUsersQueryOptions } from '@/api/generated/users/users'
import { useVisibleTeams } from '@/hooks/use-visible-teams'
import { PAGE_LIMIT } from '@/lib/pagination'
import { useMe } from '@/lib/session'
import type { RecipientNames } from './recipients'

/** `GET /users` for recipient names and the person picker; at most one page, like the add-member picker. */
export const recipientUsersQueryOptions = getListUsersQueryOptions({ limit: PAGE_LIMIT })

/** People `GET /users` returned, or none while it loads or when it fails. */
export function useRecipientUsers(enabled: boolean): { users: UserRead[]; loading: boolean } {
  const query = useQuery({ ...recipientUsersQueryOptions, enabled })
  return { users: query.data?.status === 200 ? query.data.data : [], loading: enabled && query.isPending }
}

/** Names for recipients; `GET /users` is sent only when `needUsers` is set. */
export function useRecipientNames(needUsers: boolean): RecipientNames {
  const me = useMe()
  const { teams } = useVisibleTeams()
  const { users } = useRecipientUsers(needUsers)
  return { teams, users, meId: me.user.id }
}
