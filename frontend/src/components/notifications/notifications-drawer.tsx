import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Inbox, Layers, Mail, MessageSquare, Monitor, PhoneCall, TriangleAlert, XIcon } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { Channel, type DeliveryRead } from '@/api/generated/model'
import { EmptyState } from '@/components/shell/empty-state'
import { Button } from '@/components/ui/button'
import { SegmentedControl, type SegmentedOption } from '@/components/ui/segmented-control'
import { Skeleton } from '@/components/ui/skeleton'
import { unexpectedStatusMessage } from '@/lib/api'
import { layers } from '@/lib/layers'
import { motionTokens } from '@/lib/motion'
import { usePersonName } from '@/hooks/use-person-name'
import { useMe } from '@/lib/session'
import { deliveriesQueryOptions } from './deliveries-query'
import { DeliveryItem } from './delivery-item'

/** Element id of the drawer, for the toggle's `aria-controls`. */
export const NOTIFICATIONS_DRAWER_ID = 'notifications-drawer'

type Filter = 'all' | Channel

const filterOptions = [
  { value: 'all', label: 'All', icon: Layers },
  { value: Channel.email, label: 'Email', icon: Mail },
  { value: Channel.sms, label: 'SMS', icon: MessageSquare },
  { value: Channel.phone, label: 'Calls', icon: PhoneCall },
  { value: Channel.ui, label: 'App', icon: Monitor },
] as const satisfies readonly SegmentedOption<Filter>[]

const emptyTitle = {
  all: 'Nothing sent yet',
  email: 'No emails sent yet',
  sms: 'No text messages sent yet',
  phone: 'No calls made yet',
  ui: 'No in-app notifications yet',
} as const satisfies Record<Filter, string>

const OFFLINE = "Couldn't reach PagerCutie. Check your connection and try again."

/** Props for `NotificationsDrawer`. */
export interface NotificationsDrawerProps {
  open: boolean
  onClose: () => void
}

/**
 * Debug panel on the right edge of every signed-in screen: the deliveries PagerCutie sent on every channel for
 * alerts the user can see, newest first (`DEL-4`, `DEL-6`, ADR-0073). Non-modal, so the page stays usable while it
 * is open; Escape inside it closes it.
 */
export function NotificationsDrawer({ open, onClose }: NotificationsDrawerProps) {
  const [filter, setFilter] = useState<Filter>('all')
  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          id={NOTIFICATIONS_DRAWER_ID}
          aria-label="Sent notifications"
          className="fixed inset-y-0 right-0 flex w-[380px] max-w-full flex-col border-l bg-background shadow-popover"
          style={{ zIndex: layers.drawer }}
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0, transition: motionTokens.base }}
          exit={{ opacity: 0, x: 24, transition: motionTokens.exit }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') onClose()
          }}
        >
          <header className="flex shrink-0 flex-col gap-3 border-b px-4 pt-4 pb-3">
            <div className="flex items-start gap-2">
              <div className="flex min-w-0 flex-col gap-0.5">
                <h2 className="text-[15px]/[22px] font-[560]">Sent notifications</h2>
                <p className="text-[12px]/[16px] text-muted-foreground">
                  Every message on every channel. Email, SMS and calls are simulated, so nothing leaves PagerCutie.
                </p>
              </div>
              <Button variant="ghost" size="icon-sm" aria-label="Close sent notifications" onClick={onClose}>
                <XIcon strokeWidth={1.75} />
              </Button>
            </div>
            <SegmentedControl<Filter>
              aria-label="Channel"
              options={filterOptions}
              value={filter}
              onValueChange={setFilter}
            />
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <DeliveryList key={filter} filter={filter} />
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}

function DeliveryList({ filter }: { filter: Filter }) {
  const me = useMe()
  const personName = usePersonName()
  const query = useQuery(deliveriesQueryOptions(filter === 'all' ? undefined : [filter]))

  if (query.isPending) return <DeliveriesSkeleton />
  if (query.isError) return <LoadError description={OFFLINE} onRetry={() => void query.refetch()} />
  const response = query.data
  switch (response.status) {
    case 200: {
      const deliveries = newestFirst(
        filter === 'all' ? response.data : response.data.filter((delivery) => delivery.channel === filter),
      )
      if (deliveries.length === 0) {
        return (
          <EmptyState
            icon={Inbox}
            title={emptyTitle[filter]}
            description="Messages show up here as alerts reach people."
            className="border-0"
          />
        )
      }
      return (
        <ol aria-label="Deliveries, newest first" className="flex flex-col gap-2">
          <AnimatePresence initial={false}>
            {deliveries.map((delivery) => (
              <motion.li
                key={delivery.id}
                layout
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={motionTokens.spring}
              >
                <DeliveryItem delivery={delivery} recipient={personName(delivery.user_id)} timeZone={me.user.timezone} />
              </motion.li>
            ))}
          </AnimatePresence>
        </ol>
      )
    }
    case 401:
      return <DeliveriesSkeleton />
    case 422:
      return <LoadError description="Reload the page and try again." onRetry={() => void query.refetch()} />
    default:
      return <LoadError description={unexpectedStatusMessage(response)} onRetry={() => void query.refetch()} />
  }
}

/** Sorted by `created_at`, newest first; the endpoint promises that order, the drawer keeps it for any answer. */
function newestFirst(deliveries: DeliveryRead[]): DeliveryRead[] {
  return deliveries.toSorted((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
}

function LoadError({ description, onRetry }: { description: string; onRetry: () => void }) {
  return (
    <EmptyState
      icon={TriangleAlert}
      role="alert"
      title="Couldn't load sent notifications"
      description={description}
      className="border-0"
      action={
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      }
    />
  )
}

function DeliveriesSkeleton() {
  return (
    <div data-testid="deliveries-skeleton" className="flex flex-col gap-2">
      {[0, 1, 2].map((index) => (
        <div key={index} className="flex flex-col gap-2 rounded-xl border bg-card p-3">
          <div className="flex items-center gap-2">
            <Skeleton className="size-6 rounded-full" />
            <Skeleton className="h-3 w-24" />
            <Skeleton className="ml-auto h-3 w-10" />
          </div>
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-28" />
        </div>
      ))}
    </div>
  )
}
