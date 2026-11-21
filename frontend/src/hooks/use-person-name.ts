import { useQueryClient } from '@tanstack/react-query'
import type { listTeamMembersResponse } from '@/api/generated/teams/teams'
import { getListUsersQueryKey, type listUsersResponse } from '@/api/generated/users/users'
import { useMe } from '@/lib/session'

const [usersKey] = getListUsersQueryKey()

/** How a user id reads on screen: a name, or a short id when no loaded list names the user. */
export type PersonName =
  | { kind: 'me' }
  | { kind: 'name'; name: string }
  | { kind: 'id'; shortId: string; id: string }

/**
 * Names user ids from what the cache already holds: the signed-in user, `GET /teams/{id}/members` and `GET /users`
 * answers loaded on other screens. It sends no request, so a page with many people costs nothing extra; an unknown id
 * comes back as its first 8 characters.
 */
export function usePersonName(): (userId: string) => PersonName {
  const me = useMe()
  const queryClient = useQueryClient()
  const names = new Map<string, string>()
  for (const [, response] of queryClient.getQueriesData<listUsersResponse>({ queryKey: [usersKey] })) {
    if (response?.status === 200) for (const user of response.data) names.set(user.id, user.display_name)
  }
  for (const [, response] of queryClient.getQueriesData<listTeamMembersResponse>({
    predicate: ({ queryKey: [key] }) => typeof key === 'string' && /^\/api\/teams\/[^/]+\/members$/.test(key),
  })) {
    if (response?.status === 200) for (const { user } of response.data) names.set(user.id, user.display_name)
  }
  return (userId) => {
    if (userId === me.user.id) return { kind: 'me' }
    const name = names.get(userId)
    return name === undefined ? { kind: 'id', shortId: userId.slice(0, 8), id: userId } : { kind: 'name', name }
  }
}
