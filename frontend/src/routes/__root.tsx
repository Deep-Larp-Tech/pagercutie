import { lazy, Suspense } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, Outlet } from '@tanstack/react-router'
import { MotionConfig } from 'motion/react'
import { NotFoundPage } from '@/components/shell/not-found-page'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'

/** Context every route receives from the router. */
export interface RouterContext {
  queryClient: QueryClient
}

const Devtools = import.meta.env.DEV
  ? lazy(() => import('@/components/devtools'))
  : () => null

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
  notFoundComponent: RootNotFound,
})

function RootNotFound() {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-[560px] items-center p-4">
      <NotFoundPage />
    </main>
  )
}

function RootLayout() {
  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider>
        <Outlet />
        <Toaster />
        <Suspense>
          <Devtools />
        </Suspense>
      </TooltipProvider>
    </MotionConfig>
  )
}
