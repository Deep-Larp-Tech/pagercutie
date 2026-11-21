import { Mail, MessageSquare, Monitor, PhoneCall, type LucideIcon } from 'lucide-react'
import type { Channel } from '@/api/generated/model'

/** Name of each delivery channel in sentence case (`DEL-1`). */
export const channelLabel = {
  email: 'Email',
  sms: 'SMS',
  phone: 'Phone call',
  ui: 'In the app',
} as const satisfies Record<Channel, string>

/** Lucide icon of each delivery channel. */
export const channelIcon = {
  email: Mail,
  sms: MessageSquare,
  phone: PhoneCall,
  ui: Monitor,
} as const satisfies Record<Channel, LucideIcon>

/** How a delivery travels, completing "Sending …" and "Sent …". */
export const channelMeans = {
  email: 'by email',
  sms: 'by SMS',
  phone: 'by phone call',
  ui: 'in the app',
} as const satisfies Record<Channel, string>
