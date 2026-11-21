import { getRouteApi } from '@tanstack/react-router'
import { getGetMeQueryOptions } from '@/api/generated/auth/auth'
import type { MeRead } from '@/api/generated/model'

/** How long a signed-in `GET /me` answer stays fresh before a navigation fetches it again. */
const ME_STALE_MS = 30_000

/**
 * `GET /me` for the route guards (`/_app`, `/login`). Only a `200` stays fresh; any other answer is fetched again on
 * the next navigation, so a session started in another tab is picked up. The guards handle its `401` themselves.
 */
export const meQueryOptions = getGetMeQueryOptions({
  query: {
    staleTime: (query) => (query.state.data?.status === 200 ? ME_STALE_MS : 0),
    meta: { handlesUnauthorized: true },
  },
})

const appRoute = getRouteApi('/_app')

/**
 * The signed-in user, for components under the authenticated layout (`/_app`), which loads it before rendering.
 * It is route context, not a query observer: after changing the user, invalidate `meQueryOptions` and the router.
 */
export function useMe(): MeRead {
  return appRoute.useRouteContext({ select: (context) => context.me })
}

/**
 * `target` when it is a path on this origin (`/teams/x?y=1`), otherwise `/`. A crafted `?redirect=` such as
 * `//evil.com` or `/\evil.com` (browsers read both as another host) cannot send the user off-site after sign in.
 */
export function safeRedirect(target: string | undefined): string {
  if (target === undefined || !target.startsWith('/')) return '/'
  const url = new URL(target, window.location.origin)
  if (url.origin !== window.location.origin) return '/'
  return `${url.pathname}${url.search}${url.hash}`
}
