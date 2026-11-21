import { useQuery } from '@tanstack/react-query'
import { createFileRoute, Link } from '@tanstack/react-router'
import { Inbox, Layers, MessageSquare, PhoneCall, TriangleAlert } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { z } from 'zod'
import { Channel, type DeliveryRead } from '@/api/generated/model'
import { myMessagesQueryOptions } from '@/components/phone/messages-query'
import { PhoneFrame } from '@/components/phone/phone-frame'
import { PhoneMessage } from '@/components/phone/phone-message'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { Button } from '@/components/ui/button'
import { SegmentedControl, type SegmentedOption } from '@/components/ui/segmented-control'
import { Skeleton } from '@/components/ui/skeleton'
import { focusRing } from '@/components/ui/styles'
import { unexpectedStatusMessage } from '@/lib/api'
import { motionTokens } from '@/lib/motion'
import { useMe } from '@/lib/session'

const phoneSearch = z.object({
  /** Shows one channel only; omitted shows SMS and phone calls together. */
  channel: z.enum([Channel.sms, Channel.phone]).optional().catch(undefined),
})

export const Route = createFileRoute('/_app/me/phone')({
  staticData: { title: 'Phone' },
  validateSearch: phoneSearch,
  component: PhonePage,
})

type PhoneFilter = 'all' | typeof Channel.sms | typeof Channel.phone

/** Channels each filter asks `GET /me/messages` for; the phone never shows email or in-app deliveries. */
const filterChannels = {
  all: [Channel.sms, Channel.phone],
  sms: [Channel.sms],
  phone: [Channel.phone],
} as const satisfies Record<PhoneFilter, readonly Channel[]>

const filterOptions = [
  { value: 'all', label: 'All', icon: Layers },
  { value: 'sms', label: 'SMS', icon: MessageSquare },
  { value: 'phone', label: 'Calls', icon: PhoneCall },
] as const satisfies readonly SegmentedOption<PhoneFilter>[]

const emptyTitle = {
  all: 'No messages yet',
  sms: 'No text messages yet',
  phone: 'No calls yet',
} as const satisfies Record<PhoneFilter, string>

const LOAD_FAILED = "Couldn't load your messages"
const OFFLINE = "Couldn't reach PagerCutie. Check your connection and try again."

function PhonePage() {
  const me = useMe()
  const { channel } = Route.useSearch()
  const navigate = Route.useNavigate()
  const filter: PhoneFilter = channel ?? 'all'

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Phone"
        description="Text messages and calls PagerCutie sent you. The phone is simulated, so nothing reaches a real number."
      />
      <PhoneFrame
        label="Simulated phone"
        header={
          <>
            <div className="flex flex-col gap-0.5">
              <h2 className="text-[15px]/[22px] font-[560]">Messages</h2>
              {me.user.phone === null ? (
                <p className="text-[12px]/[16px] text-muted-foreground">
                  No phone number on your profile.{' '}
                  <Link to="/me/profile" className={`rounded-sm font-medium text-primary hover:underline ${focusRing}`}>
                    Add a phone number
                  </Link>
                </p>
              ) : (
                <p className="font-mono text-[12px]/[16px] text-muted-foreground tabular-nums">{me.user.phone}</p>
              )}
            </div>
            <SegmentedControl<PhoneFilter>
              aria-label="Channel"
              options={filterOptions}
              value={filter}
              onValueChange={(next) =>
                void navigate({ search: next === 'all' ? {} : { channel: next }, replace: true })
              }
            />
          </>
        }
      >
        {/* Keyed by filter, so a new filter renders its list at once and only later arrivals animate. */}
        <MessageList key={filter} filter={filter} timeZone={me.user.timezone} />
      </PhoneFrame>
    </div>
  )
}

function MessageList({ filter, timeZone }: { filter: PhoneFilter; timeZone: string }) {
  const channels: readonly Channel[] = filterChannels[filter]
  const query = useQuery(myMessagesQueryOptions([...channels]))

  if (query.isPending) return <MessagesSkeleton />
  if (query.isError) return <LoadError description={OFFLINE} onRetry={() => void query.refetch()} />
  const response = query.data
  switch (response.status) {
    case 200: {
      const messages = newestFirst(response.data.filter((delivery) => channels.includes(delivery.channel)))
      if (messages.length === 0) {
        return (
          <EmptyState
            icon={Inbox}
            title={emptyTitle[filter]}
            description="SMS and calls sent to you show up here."
            className="border-0"
          />
        )
      }
      return (
        <ol aria-label="Messages, newest first" aria-live="polite" className="flex flex-col gap-2">
          <AnimatePresence initial={false}>
            {messages.map((delivery) => (
              <motion.li
                key={delivery.id}
                layout
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={motionTokens.spring}
              >
                <PhoneMessage delivery={delivery} timeZone={timeZone} />
              </motion.li>
            ))}
          </AnimatePresence>
        </ol>
      )
    }
    case 401:
      // The QueryCache hook sends the user to sign in (ADR-0048).
      return <MessagesSkeleton />
    case 422:
      return <LoadError description="Reload the page and try again." onRetry={() => void query.refetch()} />
    default:
      return <LoadError description={unexpectedStatusMessage(response)} onRetry={() => void query.refetch()} />
  }
}

/** Sorted by `created_at`, newest first; the endpoint promises that order, the phone keeps it for any answer. */
function newestFirst(messages: DeliveryRead[]): DeliveryRead[] {
  return messages.toSorted((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
}

function LoadError({ description, onRetry }: { description: string; onRetry: () => void }) {
  return (
    <EmptyState
      icon={TriangleAlert}
      role="alert"
      title={LOAD_FAILED}
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

function MessagesSkeleton() {
  return (
    <div data-testid="messages-skeleton" className="flex flex-col gap-2">
      {[0, 1, 2].map((index) => (
        <div key={index} className="flex flex-col gap-2 rounded-xl border bg-card p-3">
          <div className="flex items-center gap-2">
            <Skeleton className="size-6 rounded-full" />
            <Skeleton className="h-3 w-16" />
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
