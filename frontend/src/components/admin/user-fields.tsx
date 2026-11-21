import { useMemo } from 'react'
import { GlobalRole } from '@/api/generated/model'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { timeZoneOptions } from '@/lib/time-zones'
import { globalRoleLabel } from './copy'

const roleItems = Object.values(GlobalRole).map((role) => ({ value: role, label: globalRoleLabel[role] }))

/** Select over every IANA time zone; typing jumps to the first zone that starts with the typed text. */
export function TimeZoneSelect({ value, onChange }: { value: string; onChange: (zone: string) => void }) {
  const zones = useMemo(() => timeZoneOptions(value), [value])
  return (
    <Select value={value} onValueChange={(zone) => zone !== null && onChange(zone)}>
      <SelectTrigger className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent className="max-h-72">
        {zones.map((zone) => (
          <SelectItem key={zone} value={zone}>
            {zone}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** Select between the global roles `user` and `admin` (DOMAIN.md §4). */
export function GlobalRoleSelect({ value, onChange }: { value: GlobalRole; onChange: (role: GlobalRole) => void }) {
  return (
    <Select items={roleItems} value={value} onValueChange={(role) => role !== null && onChange(role)}>
      <SelectTrigger className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {roleItems.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
