import { Fragment, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { DeliveryRead } from '@/api/generated/model'
import { DeliveryStatusLine } from '@/components/delivery/delivery-status'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { usePersonName } from '@/hooks/use-person-name'
import { channelIcon, channelLabel } from '@/lib/channels'
import { useMe } from '@/lib/session'
import { PersonNameText } from './person-name'

const attemptCount = new Intl.NumberFormat('en-GB')

/** Props for `DeliveryTable`. */
export interface DeliveryTableProps {
  /** The alert's deliveries, one per recipient and channel (`DEL-6`), in the order the API sent them. */
  deliveries: readonly DeliveryRead[]
}

/**
 * Who was notified about an alert and how (`DEL-6`): recipient, channel, status (DESIGN.md §5.2), attempts and the
 * last error, with the rendered message behind a disclosure button on each row.
 */
export function DeliveryTable({ deliveries }: DeliveryTableProps) {
  const me = useMe()
  const personName = usePersonName()
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  const toggle = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current)
      if (!next.delete(id)) next.add(id)
      return next
    })

  return (
    <Table aria-label="Deliveries">
      <TableHeader>
        <TableRow>
          <TableHead>Recipient</TableHead>
          <TableHead>Channel</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Attempts</TableHead>
          <TableHead>Last error</TableHead>
          <TableHead>
            <span className="sr-only">Message</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {deliveries.map((delivery) => {
          const ChannelIcon = channelIcon[delivery.channel]
          const open = expanded.has(delivery.id)
          const messageId = `delivery-message-${delivery.id}`
          return (
            <Fragment key={delivery.id}>
              <TableRow className={open ? 'border-b-0' : undefined}>
                <TableCell className="font-medium whitespace-nowrap">
                  <PersonNameText person={personName(delivery.user_id)} />
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <span className="flex items-center gap-1.5">
                    <ChannelIcon size={14} strokeWidth={1.75} aria-hidden className="text-muted-foreground" />
                    {channelLabel[delivery.channel]}
                  </span>
                </TableCell>
                <TableCell>
                  <DeliveryStatusLine
                    channel={delivery.channel}
                    status={delivery.status}
                    attempts={delivery.attempts}
                    sentAt={delivery.sent_at}
                    timeZone={me.user.timezone}
                  />
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {attemptCount.format(delivery.attempts)}
                </TableCell>
                <TableCell className="max-w-[280px] text-[12px]/[16px] break-words text-alert-red-text">
                  {delivery.last_error ?? <span className="text-muted-foreground">None</span>}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-expanded={open}
                    aria-controls={messageId}
                    onClick={() => toggle(delivery.id)}
                  >
                    {open ? <ChevronDown strokeWidth={1.75} /> : <ChevronRight strokeWidth={1.75} />}
                    {open ? 'Hide message' : 'Show message'}
                  </Button>
                </TableCell>
              </TableRow>
              {open && (
                <TableRow>
                  <TableCell colSpan={6} className="h-auto pt-0 pb-3">
                    <pre
                      id={messageId}
                      className="rounded-md bg-muted p-3 font-mono text-[13px]/[20px] font-[450] whitespace-pre-wrap"
                    >
                      {delivery.message}
                    </pre>
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}
