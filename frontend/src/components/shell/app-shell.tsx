import { useState } from 'react'
import { CatchBoundary, Outlet, useLocation } from '@tanstack/react-router'
import { Menu } from 'lucide-react'
import { motion } from 'motion/react'
import { screenEnter } from '@/lib/motion'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Header } from './header'
import { ScreenError } from './screen-error'
import { Sidebar } from './sidebar'

/** Navigation sheet for screens below 1024 px; focus stays inside while open and returns to the button on close. */
function NavSheet() {
  const [open, setOpen] = useState(false)
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button variant="ghost" size="icon-md" aria-label="Open navigation" />}>
        <Menu strokeWidth={1.75} />
      </SheetTrigger>
      <SheetContent>
        <SheetTitle className="sr-only">Navigation</SheetTitle>
        <Sidebar onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  )
}

/**
 * Layout of every signed-in screen: a 240 px sidebar from 1024 px (a sheet below), the header, and the page in a
 * column at most 1120 px wide. A screen that throws shows `ScreenError` in the content area and keeps the shell.
 */
export function AppShell() {
  const pathname = useLocation({ select: (location) => location.pathname })
  return (
    <div className="min-h-svh bg-background lg:grid lg:grid-cols-[240px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-svh border-r lg:block">
        <Sidebar />
      </aside>
      <div className="flex min-w-0 flex-col">
        <Header navTrigger={<NavSheet />} />
        <main className="mx-auto w-full max-w-[1120px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <CatchBoundary getResetKey={() => pathname} errorComponent={ScreenError}>
            {/* Keyed by path only, so filter changes in the search params don't replay it. */}
            <motion.div key={pathname} {...screenEnter}>
              <Outlet />
            </motion.div>
          </CatchBoundary>
        </main>
      </div>
    </div>
  )
}
