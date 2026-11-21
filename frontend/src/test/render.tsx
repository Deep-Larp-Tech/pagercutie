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
import type { RouterContext } from '@/routes/__root'

/** Options for `renderWithProviders`. */
export interface RenderOptions {
  /** Path the memory router starts at and mounts `ui` on, e.g. `/teams/payments/alerts`. Defaults to `/`. */
  route?: string
}

/**
 * Renders `ui` inside a fresh QueryClient (no retries, so error states show at once) and a memory-history router
 * with one route at `route`. Find elements with `findBy*`: the router renders after it resolves the route.
 */
export function renderWithProviders(ui: ReactElement, { route = '/' }: RenderOptions = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const rootRoute = createRootRouteWithContext<RouterContext>()()
  const testRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: new URL(route, 'http://localhost').pathname,
    component: () => ui,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([testRoute]),
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
