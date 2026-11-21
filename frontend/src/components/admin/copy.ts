import type { GlobalRole } from '@/api/generated/model'

/** Label of each global role in the UI. */
export const globalRoleLabel = {
  admin: 'Admin',
  user: 'User',
} as const satisfies Record<GlobalRole, string>

/** Helper text under the time zone field. */
export const TIME_ZONE_HELP = 'Working hours and rotation times use this zone.'

/** Helper text under the phone field; the number must match E.164 (`DEL-4`). */
export const PHONE_HELP = 'Optional. Used for SMS and calls. International format, for example +420601234567.'

/** Shown when a phone number does not match E.164. */
export const PHONE_INVALID = 'Enter the number in international format, for example +420601234567.'
