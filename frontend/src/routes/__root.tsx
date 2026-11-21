import { lazy, Suspense } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, Outlet } from '@tanstack/react-router'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'

/** Context every route receives from the router. */
export interface RouterContext {
  queryClient: QueryClient
}

// Dynamic imports keep both devtools out of the production bundle.
const Devtools = import.meta.env.DEV
  ? lazy(() => import('@/components/devtools'))
  : () => null

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
})

function RootLayout() {
  return (
    <TooltipProvider>
      <Outlet />
      <Toaster />
      <Suspense>
        <Devtools />
      </Suspense>
    </TooltipProvider>
  )
}
