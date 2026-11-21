import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, GripVertical, X } from 'lucide-react'
import { Reorder, useDragControls } from 'motion/react'
import { Controller, useForm, useWatch, type Control } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Weekday, type MemberRead, type OnCallRead, type Rotation } from '@/api/generated/model'
import {
  getGetTeamOnCallQueryKey,
  getGetTeamOnCallQueryOptions,
  getGetTeamRotationQueryKey,
  getGetTeamRotationQueryOptions,
  getListTeamMembersQueryOptions,
  useSetTeamRotation,
} from '@/api/generated/teams/teams'
import {
  setTeamRotationBodyHandoffDayDefault,
  setTeamRotationBodyHandoffTimeDefault,
  setTeamRotationBodyTimezoneDefault,
  setTeamRotationBodyUserIdsMax,
} from '@/api/generated/teams/teams.zod'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Combobox, ComboboxContent, ComboboxInput, ComboboxItem } from '@/components/ui/combobox'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { unexpectedStatusMessage } from '@/lib/api'
import { HOUR_MINUTE, toHourMinute, WEEK, weekdayName } from '@/lib/local-time'
import {
  formatShiftTime,
  isTimeZone,
  upcomingShifts,
  type OnCallAnchor,
  type RotationPlan,
} from '@/lib/rotation'
import { bodyIssues } from '@/lib/validation-errors'
import { LOAD_REJECTED, OFFLINE, SAVE_FORBIDDEN, SAVE_REJECTED, TEAM_GONE } from './messages'
import { FormError, Section, SectionError, SectionSkeleton } from './section'
import { useTeamSettings } from './use-team-settings'

/** Shifts the preview lists. */
const PREVIEW_SHIFTS = 4

const UNKNOWN_PERSON = 'Someone no longer in the team'

const rotationSchema = z.object({
  user_ids: z
    .array(z.string())
    .min(1, 'Add at least one person to the rotation.')
    .max(setTeamRotationBodyUserIdsMax, `A rotation holds at most ${setTeamRotationBodyUserIdsMax} people.`),
  handoff_day: z.enum(Weekday),
  handoff_time: z.string().regex(HOUR_MINUTE, 'Enter a time as HH:MM, e.g. 09:00.'),
  timezone: z.string().refine(isTimeZone, 'Pick a time zone from the list.'),
}) satisfies z.ZodType<RotationPlan>

const dayItems = WEEK.map((value) => ({ value, label: weekdayName[value] }))

let timeZones: string[] | undefined

/** IANA zones the browser knows, plus `UTC`, which some browsers leave out of `supportedValuesOf`. */
function allTimeZones(): string[] {
  if (timeZones === undefined) {
    const zones = Intl.supportedValuesOf('timeZone')
    timeZones = zones.includes('UTC') ? zones : ['UTC', ...zones]
  }
  return timeZones
}

/** The viewer's own time zone, for times shown before a rotation exists. */
function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

/** The form values for `rotation`; a team without one starts from the API defaults in `zone`. */
function toPlan(rotation: Rotation | null, zone: string = setTeamRotationBodyTimezoneDefault): RotationPlan {
  return {
    user_ids: rotation?.user_ids ?? [],
    handoff_day: rotation?.handoff_day ?? setTeamRotationBodyHandoffDayDefault,
    handoff_time: toHourMinute(rotation?.handoff_time ?? setTeamRotationBodyHandoffTimeDefault),
    timezone: rotation?.timezone ?? zone,
  }
}

function anchorOf(onCall: OnCallRead | undefined): OnCallAnchor | undefined {
  if (onCall === undefined || onCall.user === null || onCall.until === null) return undefined
  return { userId: onCall.user.id, until: new Date(onCall.until) }
}

type NameOf = (userId: string) => string

/** `/teams/$team/settings/rotation`: who is on call now, the weekly rotation (`DEL-3`) and its next shifts. */
export function RotationSettings() {
  const { team, canEdit } = useTeamSettings()
  const rotationQuery = useQuery(getGetTeamRotationQueryOptions(team.id))
  const membersQuery = useQuery(getListTeamMembersQueryOptions(team.id))
  const onCallQuery = useQuery(getGetTeamOnCallQueryOptions(team.id))

  const members = membersQuery.data?.status === 200 ? membersQuery.data.data : []
  const names = new Map(members.map((member) => [member.user.id, member.user.display_name]))
  const nameOf: NameOf = (userId) => names.get(userId) ?? UNKNOWN_PERSON
  const savedRotation = rotationQuery.data?.status === 200 ? rotationQuery.data.data : null
  const onCall = onCallQuery.data?.status === 200 ? onCallQuery.data.data : undefined

  let body
  if (rotationQuery.isPending || membersQuery.isPending) body = <SectionSkeleton rows={4} />
  else if (rotationQuery.isError || membersQuery.isError) {
    body = (
      <SectionError
        message={OFFLINE}
        onRetry={() => {
          void rotationQuery.refetch()
          void membersQuery.refetch()
        }}
      />
    )
  } else {
    const response = rotationQuery.data
    switch (response.status) {
      case 200:
        body = canEdit ? (
          <RotationEditor
            key={JSON.stringify(response.data)}
            rotation={response.data}
            members={members}
            nameOf={nameOf}
            onCall={onCall}
          />
        ) : (
          <RotationReadOnly rotation={response.data} nameOf={nameOf} onCall={onCall} />
        )
        break
      case 401:
        body = null
        break
      case 404:
        body = <SectionError message={TEAM_GONE} />
        break
      case 422:
        body = <SectionError message={LOAD_REJECTED} />
        break
      default:
        body = (
          <SectionError message={unexpectedStatusMessage(response)} onRetry={() => void rotationQuery.refetch()} />
        )
    }
  }

  let onCallBody
  if (onCallQuery.isPending) onCallBody = <SectionSkeleton rows={1} />
  else if (onCallQuery.isError) onCallBody = <SectionError message={OFFLINE} onRetry={() => void onCallQuery.refetch()} />
  else {
    const response = onCallQuery.data
    switch (response.status) {
      case 200:
        onCallBody = <OnCallNow onCall={response.data} timeZone={savedRotation?.timezone} />
        break
      case 401:
        onCallBody = null
        break
      case 404:
        onCallBody = <SectionError message={TEAM_GONE} />
        break
      case 422:
        onCallBody = <SectionError message={LOAD_REJECTED} />
        break
      default:
        onCallBody = (
          <SectionError message={unexpectedStatusMessage(response)} onRetry={() => void onCallQuery.refetch()} />
        )
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <Section title="On call now">{onCallBody}</Section>
      <Section
        title="Rotation"
        description="People take turns being on call for a week. The next person takes over at the handoff time."
      >
        {body}
      </Section>
    </div>
  )
}

function OnCallNow({ onCall, timeZone }: { onCall: OnCallRead; timeZone: string | undefined }) {
  const { me } = useTeamSettings()
  if (onCall.user === null) return <p className="text-muted-foreground">No one is on call. The team has no rotation yet.</p>
  const who = onCall.user.id === me.user.id ? 'You are' : `${onCall.user.display_name} is`
  const zone = timeZone !== undefined && isTimeZone(timeZone) ? timeZone : browserTimeZone()
  return (
    <p data-testid="on-call-now">
      <span className="font-[560]">{who} on call</span>
      {onCall.until !== null && (
        <>
          {' until '}
          <time dateTime={onCall.until} className="tabular-nums">
            {formatShiftTime(new Date(onCall.until), zone)}
          </time>
        </>
      )}
      .
    </p>
  )
}

function handoffSentence(plan: RotationPlan): string {
  return `Hands over every ${weekdayName[plan.handoff_day]} at ${plan.handoff_time}, ${plan.timezone} time.`
}

interface RotationReadOnlyProps {
  rotation: Rotation | null
  nameOf: NameOf
  onCall: OnCallRead | undefined
}

function RotationReadOnly({ rotation, nameOf, onCall }: RotationReadOnlyProps) {
  if (rotation === null) return <p className="text-muted-foreground">No rotation yet. A team lead can set one up.</p>
  const plan = toPlan(rotation)
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <ol className="flex list-decimal flex-col gap-1 pl-5" aria-label="Rotation order">
          {plan.user_ids.map((userId) => (
            <li key={userId}>{nameOf(userId)}</li>
          ))}
        </ol>
        <p className="text-muted-foreground">{handoffSentence(plan)}</p>
      </div>
      <ShiftPreview plan={plan} nameOf={nameOf} anchor={anchorOf(onCall)} />
    </div>
  )
}

interface ShiftPreviewProps {
  plan: RotationPlan
  nameOf: NameOf
  /** The saved rotation's current on-call user; without it the preview starts as a fresh save would. */
  anchor: OnCallAnchor | undefined
  /** The form holds unsaved changes, so the preview shows what saving would do. */
  pending?: boolean
}

function ShiftPreview({ plan, nameOf, anchor, pending = false }: ShiftPreviewProps) {
  const [now] = useState(() => new Date())
  const valid = plan.user_ids.length > 0 && HOUR_MINUTE.test(plan.handoff_time) && isTimeZone(plan.timezone)
  const title = pending ? 'Next four shifts after you save' : 'Next four shifts'
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[15px]/[22px] font-semibold">{title}</h3>
      {valid ? (
        <>
          <ol className="flex flex-col divide-y rounded-lg border" aria-label={title}>
            {upcomingShifts(plan, now, PREVIEW_SHIFTS, pending ? undefined : anchor).map((shift) => (
              <li
                key={shift.start.toISOString()}
                className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-3 py-2"
              >
                <span className="font-medium">{nameOf(shift.userId)}</span>
                <span className="font-mono text-[13px]/[20px] text-muted-foreground tabular-nums">
                  {shift.start === now ? 'Now' : formatShiftTime(shift.start, plan.timezone)} to{' '}
                  {formatShiftTime(shift.end, plan.timezone)}
                </span>
              </li>
            ))}
          </ol>
          <p className="text-[12px]/[16px] text-muted-foreground">Times in {plan.timezone}.</p>
        </>
      ) : (
        <p className="text-muted-foreground">Add people and a valid handoff time to see the next shifts.</p>
      )}
    </div>
  )
}

interface RotationEditorProps {
  rotation: Rotation | null
  members: MemberRead[]
  nameOf: NameOf
  onCall: OnCallRead | undefined
}

function RotationEditor({ rotation, members, nameOf, onCall }: RotationEditorProps) {
  const { team, me } = useTeamSettings()
  const queryClient = useQueryClient()
  const save = useSetTeamRotation()
  const form = useForm<RotationPlan>({
    resolver: zodResolver(rotationSchema),
    defaultValues: toPlan(rotation, isTimeZone(me.user.timezone) ? me.user.timezone : undefined),
  })
  const { errors, isSubmitting, isDirty } = form.formState
  const plan = useWatch({ control: form.control }) satisfies Partial<RotationPlan>

  const onSubmit = form.handleSubmit(async (values) => {
    const response = await save.mutateAsync({ teamId: team.id, data: values }).catch(() => null)
    if (response === null) {
      form.setError('root', { message: OFFLINE })
      return
    }
    switch (response.status) {
      case 200:
        form.reset(toPlan(response.data))
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: getGetTeamRotationQueryKey(team.id) }),
          queryClient.invalidateQueries({ queryKey: getGetTeamOnCallQueryKey(team.id) }),
        ])
        toast.success('Rotation saved')
        return
      case 400:
        form.setError('root', { message: SAVE_REJECTED })
        return
      case 401:
        return
      case 403:
        form.setError('root', { message: SAVE_FORBIDDEN })
        return
      case 404:
        form.setError('root', { message: TEAM_GONE })
        return
      case 422: {
        const issues = bodyIssues(response.data)
        if (issues.length === 0) form.setError('root', { message: SAVE_REJECTED })
        for (const { path, message } of issues) {
          const field = path[0]
          if (field === 'user_ids' || field === 'handoff_day' || field === 'handoff_time' || field === 'timezone') {
            form.setError(field, { message })
          } else form.setError('root', { message })
        }
        return
      }
      default:
        form.setError('root', { message: unexpectedStatusMessage(response) })
    }
  })

  const previewPlan: RotationPlan = {
    user_ids: plan.user_ids ?? [],
    handoff_day: plan.handoff_day ?? setTeamRotationBodyHandoffDayDefault,
    handoff_time: plan.handoff_time ?? '',
    timezone: plan.timezone ?? '',
  }

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-6">
      <RotationOrder control={form.control} members={members} nameOf={nameOf} onCallUserId={isDirty ? undefined : onCall?.user?.id} />
      <div className="flex flex-wrap items-start gap-x-6 gap-y-4">
        <Controller
          control={form.control}
          name="handoff_day"
          render={({ field, fieldState }) => (
            <Field className="w-auto" invalid={fieldState.error !== undefined}>
              <FieldLabel>Handoff day</FieldLabel>
              <Select items={dayItems} value={field.value} onValueChange={(next) => next !== null && field.onChange(next)}>
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {dayItems.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {fieldState.error?.message !== undefined && <FieldError>{fieldState.error.message}</FieldError>}
            </Field>
          )}
        />
        <Field className="w-36" invalid={errors.handoff_time !== undefined}>
          <FieldLabel>Handoff time</FieldLabel>
          <Input
            inputMode="numeric"
            autoComplete="off"
            placeholder="HH:MM"
            className="font-mono tabular-nums"
            {...form.register('handoff_time')}
          />
          {errors.handoff_time?.message !== undefined && <FieldError>{errors.handoff_time.message}</FieldError>}
        </Field>
        <Controller
          control={form.control}
          name="timezone"
          render={({ field, fieldState }) => (
            <Field className="w-full max-w-[280px]" invalid={fieldState.error !== undefined}>
              <FieldLabel>Time zone</FieldLabel>
              <Combobox
                items={allTimeZones()}
                value={field.value === '' ? null : field.value}
                onValueChange={(next) => field.onChange(next ?? '')}
              >
                <ComboboxInput placeholder="Search, e.g. Prague" />
                <ComboboxContent empty="No time zone matches.">
                  {(zone: string) => (
                    <ComboboxItem key={zone} value={zone}>
                      {zone}
                    </ComboboxItem>
                  )}
                </ComboboxContent>
              </Combobox>
              {fieldState.error?.message !== undefined && <FieldError>{fieldState.error.message}</FieldError>}
            </Field>
          )}
        />
      </div>
      <ShiftPreview plan={previewPlan} nameOf={nameOf} anchor={anchorOf(onCall)} pending={isDirty || rotation === null} />
      {errors.root?.message !== undefined && <FormError>{errors.root.message}</FormError>}
      <div>
        <Button type="submit" disabled={isSubmitting || !isDirty}>
          {isSubmitting ? 'Saving…' : 'Save rotation'}
        </Button>
      </div>
    </form>
  )
}

interface RotationOrderProps {
  control: Control<RotationPlan>
  members: MemberRead[]
  nameOf: NameOf
  /** Marked "On call now" while the order matches the saved rotation. */
  onCallUserId: string | undefined
}

/** The rotation's people in order: drag a row by its handle, or use the move buttons from the keyboard. */
function RotationOrder({ control, members, nameOf, onCallUserId }: RotationOrderProps) {
  const [picked, setPicked] = useState<string | null>(null)
  return (
    <Controller
      control={control}
      name="user_ids"
      render={({ field, fieldState }) => {
        const ids = field.value
        const move = (from: number, to: number) => {
          const next = [...ids]
          const [moved] = next.splice(from, 1)
          next.splice(to, 0, moved)
          field.onChange(next)
        }
        const addable = members.filter(({ user, role }) => role !== 'viewer' && !ids.includes(user.id))
        const addItems = addable.map(({ user }) => ({ value: user.id, label: user.display_name }))
        return (
          <div className="flex flex-col gap-3">
            {ids.length === 0 ? (
              <p className="text-muted-foreground">No one is in the rotation yet.</p>
            ) : (
              <Reorder.Group
                as="ol"
                axis="y"
                values={ids}
                onReorder={field.onChange}
                aria-label="Rotation order"
                className="flex max-w-[560px] flex-col gap-2"
              >
                {ids.map((userId, index) => (
                  <RotationRow
                    key={userId}
                    userId={userId}
                    index={index}
                    count={ids.length}
                    name={nameOf(userId)}
                    onCall={userId === onCallUserId}
                    onMove={(to) => move(index, to)}
                    onRemove={() => field.onChange(ids.filter((id) => id !== userId))}
                  />
                ))}
              </Reorder.Group>
            )}
            {fieldState.error?.message !== undefined && <FormError>{fieldState.error.message}</FormError>}
            <Field className="w-auto">
              <FieldLabel>Add to rotation</FieldLabel>
              <Select
                items={addItems}
                value={picked}
                disabled={addItems.length === 0}
                onValueChange={(userId) => {
                  if (userId === null) return
                  field.onChange([...ids, userId])
                  setPicked(null)
                }}
              >
                <SelectTrigger className="w-60">
                  <SelectValue placeholder={addItems.length === 0 ? 'Everyone is in the rotation' : 'Pick a person'} />
                </SelectTrigger>
                <SelectContent>
                  {addItems.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>
        )
      }}
    />
  )
}

interface RotationRowProps {
  userId: string
  index: number
  count: number
  name: string
  onCall: boolean
  onMove: (to: number) => void
  onRemove: () => void
}

function RotationRow({ userId, index, count, name, onCall, onMove, onRemove }: RotationRowProps) {
  const controls = useDragControls()
  return (
    <Reorder.Item
      as="li"
      value={userId}
      dragListener={false}
      dragControls={controls}
      className="relative flex items-center gap-2 rounded-lg border bg-card py-1.5 pr-1.5 pl-1 text-card-foreground"
    >
      <span
        aria-hidden
        onPointerDown={(event) => controls.start(event)}
        className="flex h-7 w-6 cursor-grab touch-none items-center justify-center text-muted-foreground active:cursor-grabbing"
      >
        <GripVertical size={16} strokeWidth={1.75} />
      </span>
      <span className="w-5 text-right font-mono text-[13px]/[20px] text-muted-foreground tabular-nums">
        {index + 1}
      </span>
      <span className="min-w-0 flex-1 truncate font-medium">{name}</span>
      {onCall && <Badge>On call now</Badge>}
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={`Move ${name} up`}
        disabled={index === 0}
        onClick={() => onMove(index - 1)}
      >
        <ArrowUp strokeWidth={1.75} />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={`Move ${name} down`}
        disabled={index === count - 1}
        onClick={() => onMove(index + 1)}
      >
        <ArrowDown strokeWidth={1.75} />
      </Button>
      <Button type="button" variant="ghost" size="icon-sm" aria-label={`Remove ${name} from the rotation`} onClick={onRemove}>
        <X strokeWidth={1.75} />
      </Button>
    </Reorder.Item>
  )
}
