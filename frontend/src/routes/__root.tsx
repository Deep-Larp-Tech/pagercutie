import { lazy, Suspense } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, Outlet } from '@tanstack/react-router'
import { NotFoundPage } from '@/components/shell/not-found-page'
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
  notFoundComponent: RootNotFound,
})

// Unknown paths under the signed-in layout hit its splat route (`_app/$.tsx`) and keep the shell; this covers the rest.
function RootNotFound() {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-[560px] items-center p-4">
      <NotFoundPage />
    </main>
  )
}

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
