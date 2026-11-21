import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { getMeResponse } from '@/api/generated/auth/auth'
import type { MeRead } from '@/api/generated/model'
import { createApp } from '@/router'
import type { RouterContext } from '@/routes/__root'
import { meQueryOptions } from '@/lib/session'

/** Options for `renderWithProviders`. */
export interface RenderOptions {
  /** Path the memory router starts at and mounts `ui` on, e.g. `/teams/payments/alerts`. Defaults to `/`. */
  route?: string
  /** Signed-in user: mounts `ui` under a layout with the id `/_app`, so `useMe()` returns it, and seeds `GET /me`. */
  me?: MeRead
}

/**
 * Renders `ui` inside a fresh QueryClient (no retries, so error states show at once) and a memory-history router
 * with one route at `route`. Find elements with `findBy*`: the router renders after it resolves the route.
 */
export function renderWithProviders(ui: ReactElement, { route = '/', me }: RenderOptions = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const rootRoute = createRootRouteWithContext<RouterContext>()()
  const path = new URL(route, 'http://localhost').pathname
  let routeTree
  if (me === undefined) {
    routeTree = rootRoute.addChildren([
      createRoute({ getParentRoute: () => rootRoute, path, component: () => ui }),
    ])
  } else {
    const response: getMeResponse = { status: 200, data: me, headers: new Headers() }
    queryClient.setQueryData(meQueryOptions.queryKey, response)
    // Same id as `routes/_app.tsx`, which is what `useMe()` reads the context from.
    const appRoute = createRoute({ getParentRoute: () => rootRoute, id: '_app', beforeLoad: () => ({ me }) })
    routeTree = rootRoute.addChildren([
      appRoute.addChildren([createRoute({ getParentRoute: () => appRoute, path, component: () => ui })]),
    ])
  }
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [route] }),
    context: { queryClient },
  })
  const user = userEvent.setup()
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...result, user, queryClient, router }
}

/**
 * Renders the real app (route tree, route guards, the `401` redirect) on a memory history that starts at `route`,
 * e.g. `/login?redirect=%2Fteams`. Declare `GET /me` in every test: the `/_app` and `/login` guards call it.
 */
export function renderApp(route: string) {
  const { queryClient, router } = createApp(createMemoryHistory({ initialEntries: [route] }))
  const user = userEvent.setup()
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...result, user, queryClient, router }
}
