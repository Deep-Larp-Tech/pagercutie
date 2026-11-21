import type { QueryClient } from '@tanstack/react-query'
import { createRouter, type RouterHistory } from '@tanstack/react-router'
import { getGetMeQueryKey } from './api/generated/auth/auth'
import { createQueryClient } from './lib/query'
import { routeTree } from './routeTree.gen'

/** Creates the app router from the generated file-based route tree; the QueryClient rides in its context. */
export function createAppRouter(queryClient: QueryClient, history?: RouterHistory) {
  return createRouter({
    routeTree,
    context: { queryClient },
    history,
    defaultPreload: 'intent',
    scrollRestoration: true,
  })
}

/** The app router. */
export type AppRouter = ReturnType<typeof createAppRouter>

/**
 * Creates the QueryClient and the router together and sends the user to `/login?redirect=<current page>` when a
 * query or mutation answers `401` (ADR-0048). `history` defaults to the browser's; tests pass a memory history.
 */
export function createApp(history?: RouterHistory): { queryClient: QueryClient; router: AppRouter } {
  const queryClient = createQueryClient({ onUnauthorized: () => signInAgain(router, queryClient) })
  const router = createAppRouter(queryClient, history)
  return { queryClient, router }
}

function signInAgain(router: AppRouter, queryClient: QueryClient) {
  const { pathname, href } = router.state.location
  if (pathname === '/login') return
  // A cached signed-in `GET /me` would make /login send the user straight back.
  queryClient.removeQueries({ queryKey: getGetMeQueryKey() })
  void router.navigate({ to: '/login', search: { redirect: href }, replace: true })
}

declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter
  }
}
