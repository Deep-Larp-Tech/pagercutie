import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Channel, type Recipient, type UserRead } from '@/api/generated/model'
import { createRuleBodyRoutingRecipientsMax } from '@/api/generated/rules/rules.zod'
import { Button } from '@/components/ui/button'
import { Combobox, ComboboxContent, ComboboxInput, ComboboxItem } from '@/components/ui/combobox'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { channelLabel } from '@/lib/channels'
import type { VisibleTeam } from '@/lib/teams'
import { describeRecipient, recipientTypeLabel, sameRecipient } from './recipients'
import type { RuleScope } from './rule-scope'
import { useRecipientNames, useRecipientUsers } from './use-recipient-names'

const CHANNELS: readonly Channel[] = Object.values(Channel)

const typeItems = (['on_call', 'team', 'user'] as const).map((type) => ({ value: type, label: recipientTypeLabel[type] }))

/** Props for `RecipientsEditor`. */
export interface RecipientsEditorProps {
  scope: RuleScope
  recipients: Recipient[]
  onRecipients: (recipients: Recipient[]) => void
  /** `null` uses each recipient's channel preferences. */
  channels: Channel[] | null
  onChannels: (channels: Channel[] | null) => void
  recipientsError?: string
  channelsError?: string
  readOnly: boolean
}

/**
 * Who a rule notifies and how (`RUL-3`, DOMAIN.md §5): users, whole teams or a team's on-call person, and optionally
 * channels that override everyone's preferences. A personal rule notifies only its owner (ADR-0026), so it shows the
 * channels only.
 */
export function RecipientsEditor({
  scope,
  recipients,
  onRecipients,
  channels,
  onChannels,
  recipientsError,
  channelsError,
  readOnly,
}: RecipientsEditorProps) {
  const names = useRecipientNames(scope.kind === 'team' && recipients.some(({ type }) => type === 'user'))
  return (
    <div className="flex flex-col gap-6">
      {scope.kind === 'personal' ? (
        <p>This rule notifies only you.</p>
      ) : (
        <div className="flex flex-col gap-3">
          <span className="font-medium">Recipients</span>
          {recipients.length === 0 ? (
            <p className="text-muted-foreground">No one yet.</p>
          ) : (
            <ul aria-label="Recipients" className="flex flex-col gap-1">
              {recipients.map((recipient) => {
                const name = describeRecipient(recipient, names)
                return (
                  <li key={`${recipient.type}-${recipient.type === 'user' ? recipient.user_id : recipient.team_id}`} className="flex h-8 max-w-[480px] items-center justify-between gap-2 border-b">
                    <span>{name}</span>
                    {!readOnly && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${name}`}
                        onClick={() => onRecipients(recipients.filter((other) => !sameRecipient(other, recipient)))}
                      >
                        <Trash2 strokeWidth={1.75} />
                      </Button>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          {recipientsError !== undefined && (
            <p className="text-[12px]/[16px] font-medium text-alert-red-text">{recipientsError}</p>
          )}
          {!readOnly && (
            <AddRecipient
              teams={names.teams}
              defaultTeamId={scope.team.id}
              full={recipients.length >= createRuleBodyRoutingRecipientsMax}
              onAdd={(recipient) => {
                if (!recipients.some((other) => sameRecipient(other, recipient))) onRecipients([...recipients, recipient])
              }}
            />
          )}
        </div>
      )}

      <Field invalid={channelsError !== undefined} className="gap-3">
        <label className="flex w-fit items-center gap-2">
          <Switch checked={channels === null} disabled={readOnly} onCheckedChange={(checked) => onChannels(checked ? null : [])} />
          Use each person's notification settings
        </label>
        <FieldDescription>
          {channels === null
            ? 'Each recipient gets the alert on the channels their settings pick for its severity.'
            : 'Everyone gets the alert on the channels below, whatever their settings say.'}
        </FieldDescription>
        {channels !== null && (
          <ToggleGroup
            multiple
            size="md"
            aria-label="Channels"
            disabled={readOnly}
            value={channels}
            onValueChange={(next) => onChannels(CHANNELS.filter((channel) => next.includes(channel)))}
          >
            {CHANNELS.map((channel) => (
              <ToggleGroupItem key={channel} value={channel}>
                {channelLabel[channel]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        )}
        {channelsError !== undefined && <FieldError>{channelsError}</FieldError>}
      </Field>
    </div>
  )
}

interface AddRecipientProps {
  teams: readonly VisibleTeam[]
  defaultTeamId: string
  full: boolean
  onAdd: (recipient: Recipient) => void
}

function AddRecipient({ teams, defaultTeamId, full, onAdd }: AddRecipientProps) {
  const [type, setType] = useState<Recipient['type']>('on_call')
  const [teamId, setTeamId] = useState(defaultTeamId)
  const [user, setUser] = useState<UserRead | null>(null)
  const { users, loading } = useRecipientUsers(type === 'user')
  const teamItems = teams.map(({ team }) => ({ value: team.id, label: team.name }))

  const recipient: Recipient | null =
    type === 'user' ? (user === null ? null : { type: 'user', user_id: user.id }) : { type, team_id: teamId }

  return (
    <div className="flex flex-wrap items-end gap-2">
      <Field className="w-auto">
        <FieldLabel>Notify</FieldLabel>
        <Select items={typeItems} value={type} onValueChange={(next) => next !== null && setType(next)}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {typeItems.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      {type === 'user' ? (
        <Field className="w-64">
          <FieldLabel>Person</FieldLabel>
          <Combobox<UserRead>
            items={users}
            value={user}
            onValueChange={setUser}
            itemToStringLabel={(item) => item.display_name}
            isItemEqualToValue={(a, b) => a.id === b.id}
          >
            <ComboboxInput placeholder="Type a name" />
            <ComboboxContent empty={loading ? 'Loading people…' : 'No one matches.'}>
              {(item: UserRead) => (
                <ComboboxItem key={item.id} value={item}>
                  {item.display_name}
                  <span className="truncate text-[12px]/[16px] text-muted-foreground">{item.email}</span>
                </ComboboxItem>
              )}
            </ComboboxContent>
          </Combobox>
        </Field>
      ) : (
        <Field className="w-auto">
          <FieldLabel>Team</FieldLabel>
          <Select items={teamItems} value={teamId} onValueChange={(next) => next !== null && setTeamId(next)}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {teamItems.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      )}
      <Button
        type="button"
        variant="secondary"
        disabled={recipient === null || full}
        onClick={() => {
          if (recipient === null) return
          onAdd(recipient)
          setUser(null)
        }}
      >
        <Plus strokeWidth={1.75} aria-hidden />
        Add recipient
      </Button>
    </div>
  )
}
