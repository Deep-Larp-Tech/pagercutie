import { useState } from 'react'
import { CatchBoundary, Outlet, useLocation, useMatches } from '@tanstack/react-router'
import { Inbox, Menu } from 'lucide-react'
import { motion } from 'motion/react'
import { screenEnter } from '@/lib/motion'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { NOTIFICATIONS_DRAWER_ID, NotificationsDrawer } from '@/components/notifications/notifications-drawer'
import { useDrawerOpen } from '@/components/notifications/use-drawer-open'
import { cn } from '@/lib/utils'
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
  // A layout with `ownsTransitions` animates its children itself; keying on its path keeps it mounted meanwhile.
  const screenKey =
    useMatches({ select: (matches) => matches.findLast((match) => match.staticData.ownsTransitions)?.pathname }) ??
    pathname
  const [drawerOpen, setDrawerOpen] = useDrawerOpen()
  return (
    <div className="min-h-svh bg-background lg:grid lg:grid-cols-[240px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-svh border-r lg:block">
        <Sidebar />
      </aside>
      {/* From 1024 px the open drawer docks: the column makes room for it instead of being covered. */}
      <div className={cn('flex min-w-0 flex-col', drawerOpen && 'lg:pr-[380px]')}>
        <Header
          navTrigger={<NavSheet />}
          drawerTrigger={<DrawerToggle open={drawerOpen} onToggle={() => setDrawerOpen(!drawerOpen)} />}
        />
        <main className="mx-auto w-full max-w-[1120px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <CatchBoundary getResetKey={() => pathname} errorComponent={ScreenError}>
            {/* Keyed by path only, so filter changes in the search params don't replay it. */}
            <motion.div key={screenKey} {...screenEnter}>
              <Outlet />
            </motion.div>
          </CatchBoundary>
        </main>
      </div>
      <NotificationsDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  )
}

/** Header button that opens and closes the notifications drawer. */
function DrawerToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon-md"
            aria-label="Sent notifications"
            aria-expanded={open}
            aria-controls={NOTIFICATIONS_DRAWER_ID}
            onClick={onToggle}
            className={cn(open && 'bg-accent text-primary')}
          />
        }
      >
        <Inbox strokeWidth={1.75} />
      </TooltipTrigger>
      <TooltipContent>{open ? 'Hide sent notifications' : 'Show sent notifications'}</TooltipContent>
    </Tooltip>
  )
}
