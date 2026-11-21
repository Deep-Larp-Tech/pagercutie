import { useId } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { Controller, useFieldArray, useForm, useWatch, type Control, type FieldPath } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import {
  Channel,
  Weekday,
  type ChannelPreferences,
  type ChannelRule,
  type Severity,
} from '@/api/generated/model'
import { SetTeamChannelPreferencesBody } from '@/api/generated/teams/teams.zod'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { HOUR_MINUTE, toHourMinute, WEEK, weekdayLabel } from '@/lib/local-time'
import { channelLabel, describeRule, FALLBACK_SUMMARY, MAX_CHANNEL_RULES } from '@/lib/preferences'
import { severityIcon, severityLabel } from '@/lib/severity'
import type { BodyIssue } from '@/lib/validation-errors'

/** What saving the preferences came to; the page that owns the endpoint maps its response to this. */
export type PreferencesSaveResult =
  /** `200`: the preferences as the API stored them. */
  | { kind: 'saved'; preferences: ChannelPreferences }
  /** `422`: field errors, shown under the fields they point at. */
  | { kind: 'invalid'; issues: BodyIssue[] }
  /** Anything else, as one message under the form. */
  | { kind: 'failed'; message: string }

/** Props for `ChannelPreferencesEditor`. */
export interface ChannelPreferencesEditorProps {
  /** The saved preferences (`GET …/channel-preferences`). */
  value: ChannelPreferences
  /** Shows the rules as plain sentences without controls. */
  readOnly: boolean
  /** Sends the preferences (`PUT …/channel-preferences`) and reports the outcome. */
  onSave: (preferences: ChannelPreferences) => Promise<PreferencesSaveResult>
}

const hourMinute = z.string().regex(HOUR_MINUTE, 'Enter a time as HH:MM, e.g. 08:00.')

const generatedRule = SetTeamChannelPreferencesBody.shape.rules.unwrap().element

const preferencesSchema = z.object({
  rules: z
    .array(
      z.object({
        min_severity: generatedRule.shape.min_severity,
        channels: z.array(z.enum(Channel)).min(1, 'Pick at least one channel.'),
        window: z
          .object({
            days: z.array(z.enum(Weekday)).min(1, 'Pick at least one day.'),
            start: hourMinute,
            end: hourMinute,
          })
          .nullable(),
      }),
    )
    .max(MAX_CHANNEL_RULES, `Use at most ${MAX_CHANNEL_RULES} rules.`),
})

type PreferencesForm = z.infer<typeof preferencesSchema>
type RuleForm = PreferencesForm['rules'][number]

/** Most severe first, as people read the select. */
const SEVERITIES: readonly Severity[] = ['critical', 'error', 'warn', 'info', 'debug']
const severityItems = SEVERITIES.map((value) => ({ value, label: severityLabel[value] }))
const CHANNELS: readonly Channel[] = Object.values(Channel)

const NEW_RULE: RuleForm = { min_severity: 'critical', channels: ['email'], window: null }
const NEW_WINDOW: NonNullable<RuleForm['window']> = {
  days: ['mon', 'tue', 'wed', 'thu', 'fri'],
  start: '08:00',
  end: '20:00',
}

function toForm(value: ChannelPreferences): PreferencesForm {
  return {
    rules: (value.rules ?? []).map((rule) => ({
      min_severity: rule.min_severity,
      channels: rule.channels,
      window: rule.window
        ? {
            days: rule.window.days ?? [...WEEK],
            start: toHourMinute(rule.window.start),
            end: toHourMinute(rule.window.end),
          }
        : null,
    })),
  }
}

/** The form field a `422` error points at (`['rules', 0, 'channels']` → `rules.0.channels`), or `root`. */
function issueField(path: BodyIssue['path']): FieldPath<PreferencesForm> | 'root' {
  const [key, index, field, part] = path
  if (key !== 'rules') return 'root'
  if (typeof index !== 'number') return 'rules'
  if (field === 'min_severity' || field === 'channels') return `rules.${index}.${field}`
  if (field === 'window') {
    if (part === 'days' || part === 'start' || part === 'end') return `rules.${index}.window.${part}`
    return `rules.${index}.window`
  }
  return 'root'
}

/**
 * Ordered channel preference rules (DOMAIN.md §5, `DEL-2`): the first rule whose minimum severity and time window
 * match an alert picks its channels, and an alert no rule matches shows in the UI only. Each row shows its rule as a
 * sentence. Serves the team's preferences and a user's own (`/me/notifications`).
 */
export function ChannelPreferencesEditor({ value, readOnly, onSave }: ChannelPreferencesEditorProps) {
  if (readOnly) return <PreferencesSummary rules={value.rules ?? []} />
  return <PreferencesEditForm value={value} onSave={onSave} />
}

function PreferencesSummary({ rules }: { rules: readonly ChannelRule[] }) {
  return (
    <div className="flex flex-col gap-3">
      {rules.length === 0 ? (
        <p className="text-muted-foreground">No rules yet.</p>
      ) : (
        <ol className="flex list-decimal flex-col gap-2 pl-5">
          {rules.map((rule, index) => (
            <li key={index}>{describeRule(rule)}</li>
          ))}
        </ol>
      )}
      <p className="text-muted-foreground">{FALLBACK_SUMMARY}</p>
    </div>
  )
}

function PreferencesEditForm({ value, onSave }: Omit<ChannelPreferencesEditorProps, 'readOnly'>) {
  const form = useForm<PreferencesForm>({ resolver: zodResolver(preferencesSchema), defaultValues: toForm(value) })
  const rules = useFieldArray({ control: form.control, name: 'rules' })
  const { errors, isSubmitting, isDirty } = form.formState
  const full = rules.fields.length >= MAX_CHANNEL_RULES

  const onSubmit = form.handleSubmit(async (values) => {
    const result = await onSave(values)
    switch (result.kind) {
      case 'saved':
        form.reset(toForm(result.preferences))
        toast.success('Notification settings saved')
        return
      case 'invalid':
        if (result.issues.length === 0) {
          form.setError('root', { message: "Couldn't save the rules. Check them and try again." })
        }
        for (const { path, message } of result.issues) form.setError(issueField(path), { message })
        return
      case 'failed':
        form.setError('root', { message: result.message })
        return
      default:
        result satisfies never
    }
  })

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-4">
      {rules.fields.length === 0 ? (
        <p className="text-muted-foreground">No rules yet. Every alert shows in the UI only.</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {rules.fields.map((field, index) => (
            <RuleRow
              key={field.id}
              control={form.control}
              index={index}
              count={rules.fields.length}
              onMove={(to) => rules.move(index, to)}
              onRemove={() => rules.remove(index)}
            />
          ))}
        </ol>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="secondary" disabled={full} onClick={() => rules.append(NEW_RULE)}>
          <Plus strokeWidth={1.75} aria-hidden />
          Add rule
        </Button>
        {full && (
          <span className="text-[12px]/[16px] text-muted-foreground">
            You can add up to {MAX_CHANNEL_RULES} rules.
          </span>
        )}
      </div>
      <p className="text-muted-foreground">{FALLBACK_SUMMARY}</p>
      {(errors.root?.message ?? errors.rules?.message ?? errors.rules?.root?.message) !== undefined && (
        <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
          {errors.root?.message ?? errors.rules?.message ?? errors.rules?.root?.message}
        </p>
      )}
      <div>
        <Button type="submit" disabled={isSubmitting || !isDirty}>
          {isSubmitting ? 'Saving…' : 'Save preferences'}
        </Button>
      </div>
    </form>
  )
}

interface RuleRowProps {
  control: Control<PreferencesForm>
  index: number
  count: number
  onMove: (to: number) => void
  onRemove: () => void
}

function RuleRow({ control, index, count, onMove, onRemove }: RuleRowProps) {
  const rule = useWatch({ control, name: `rules.${index}` })
  const number = index + 1
  const titleId = useId()
  return (
    <li
      aria-labelledby={titleId}
      className="flex flex-col gap-4 rounded-lg border bg-card p-4 text-card-foreground shadow-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h3 id={titleId} className="text-[12px]/[16px] font-medium text-muted-foreground">
            Rule {number}
          </h3>
          <p className="font-[560]" data-testid="rule-summary">
            {describeRule(rule)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Move rule ${number} up`}
            disabled={index === 0}
            onClick={() => onMove(index - 1)}
          >
            <ArrowUp strokeWidth={1.75} />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Move rule ${number} down`}
            disabled={index === count - 1}
            onClick={() => onMove(index + 1)}
          >
            <ArrowDown strokeWidth={1.75} />
          </Button>
          <Button type="button" variant="ghost" size="icon-sm" aria-label={`Remove rule ${number}`} onClick={onRemove}>
            <Trash2 strokeWidth={1.75} />
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-start gap-x-6 gap-y-4">
        <Controller
          control={control}
          name={`rules.${index}.min_severity`}
          render={({ field, fieldState }) => (
            <Field className="w-auto" invalid={fieldState.error !== undefined}>
              <FieldLabel>Minimum severity</FieldLabel>
              <Select items={severityItems} value={field.value} onValueChange={(next) => next !== null && field.onChange(next)}>
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {severityItems.map((item) => {
                    const Icon = severityIcon[item.value]
                    return (
                      <SelectItem key={item.value} value={item.value}>
                        <Icon strokeWidth={1.75} aria-hidden />
                        {item.label}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
              {fieldState.error?.message !== undefined && <FieldError>{fieldState.error.message}</FieldError>}
            </Field>
          )}
        />
        <Controller
          control={control}
          name={`rules.${index}.channels`}
          render={({ field, fieldState }) => (
            <Field className="w-auto" invalid={fieldState.error !== undefined}>
              <FieldLabel render={<span />} nativeLabel={false}>
                Channels
              </FieldLabel>
              <ToggleGroup
                multiple
                size="md"
                aria-label={`Channels for rule ${number}`}
                value={field.value}
                onValueChange={field.onChange}
              >
                {CHANNELS.map((channel) => (
                  <ToggleGroupItem key={channel} value={channel}>
                    {channelLabel[channel]}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
              {fieldState.error?.message !== undefined && <FieldError>{fieldState.error.message}</FieldError>}
            </Field>
          )}
        />
      </div>

      <WindowFields control={control} index={index} number={number} />
    </li>
  )
}

interface WindowFieldsProps {
  control: Control<PreferencesForm>
  index: number
  number: number
}

function WindowFields({ control, index, number }: WindowFieldsProps) {
  return (
    <Controller
      control={control}
      name={`rules.${index}.window`}
      render={({ field: windowField, fieldState: windowState }) => (
        <div className="flex flex-col gap-3">
          <label className="flex w-fit items-center gap-2">
            <Switch
              checked={windowField.value !== null}
              onCheckedChange={(checked) => windowField.onChange(checked ? NEW_WINDOW : null)}
            />
            Only at certain times
          </label>
          {windowField.value !== null && (
            <div className="flex flex-wrap items-start gap-x-6 gap-y-4">
              <Controller
                control={control}
                name={`rules.${index}.window.days`}
                render={({ field, fieldState }) => (
                  <Field className="w-auto" invalid={fieldState.error !== undefined}>
                    <FieldLabel render={<span />} nativeLabel={false}>
                      Days
                    </FieldLabel>
                    <ToggleGroup
                      multiple
                      size="md"
                      aria-label={`Days for rule ${number}`}
                      value={field.value}
                      onValueChange={field.onChange}
                    >
                      {WEEK.map((day) => (
                        <ToggleGroupItem key={day} value={day}>
                          {weekdayLabel[day]}
                        </ToggleGroupItem>
                      ))}
                    </ToggleGroup>
                    {fieldState.error?.message !== undefined && <FieldError>{fieldState.error.message}</FieldError>}
                  </Field>
                )}
              />
              <TimeField control={control} name={`rules.${index}.window.start`} label="From" />
              <TimeField control={control} name={`rules.${index}.window.end`} label="To" />
            </div>
          )}
          {windowField.value !== null && (
            <p className="text-[12px]/[16px] text-muted-foreground">
              Times are in the owner's time zone. A window that ends before it starts runs past midnight.
            </p>
          )}
          {windowState.error?.message !== undefined && (
            <p role="alert" className="text-[12px]/[16px] font-medium text-alert-red-text">
              {windowState.error.message}
            </p>
          )}
        </div>
      )}
    />
  )
}

interface TimeFieldProps {
  control: Control<PreferencesForm>
  name: `rules.${number}.window.start` | `rules.${number}.window.end`
  label: string
}

function TimeField({ control, name, label }: TimeFieldProps) {
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field className="w-28" invalid={fieldState.error !== undefined}>
          <FieldLabel>{label}</FieldLabel>
          <Input
            inputMode="numeric"
            autoComplete="off"
            placeholder="HH:MM"
            className="font-mono tabular-nums"
            {...field}
          />
          {fieldState.error?.message !== undefined && <FieldError>{fieldState.error.message}</FieldError>}
        </Field>
      )}
    />
  )
}
