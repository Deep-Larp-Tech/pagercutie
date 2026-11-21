import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import { toast } from 'sonner'
import type { MemberRead, TeamRead, TeamRole, UserRead } from '@/api/generated/model'
import {
  getListTeamMembersQueryKey,
  getListTeamMembersQueryOptions,
  useRemoveTeamMember,
  useSetTeamMember,
} from '@/api/generated/teams/teams'
import { getListUsersQueryOptions } from '@/api/generated/users/users'
import { Button } from '@/components/ui/button'
import { Combobox, ComboboxContent, ComboboxInput, ComboboxItem } from '@/components/ui/combobox'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { unexpectedStatusMessage } from '@/lib/api'
import { isLastLead, roleLabel, TEAM_ROLES } from '@/lib/roles'
import { meQueryOptions } from '@/lib/session'
import { bodyIssues } from '@/lib/validation-errors'
import { LOAD_REJECTED, OFFLINE, SAVE_FORBIDDEN, SAVE_REJECTED, TEAM_GONE } from './messages'
import { FormError, Section, SectionError, SectionSkeleton } from './section'
import { useTeamSettings } from './use-team-settings'

/** Largest page `GET /users` allows; the add-member combobox offers at most this many people. */
const USERS_PAGE_LIMIT = 100

const roleItems = TEAM_ROLES.map((role) => ({ value: role, label: roleLabel[role] }))

/** Why the last lead's role and **Remove** are disabled. */
const LAST_LEAD_NOTE = 'Each team needs a lead. Make someone else a lead first.'

/** `/teams/$team/settings/members`: members and their roles; leads add, change and remove them. */
export function MembersSettings() {
  const { team, canEdit } = useTeamSettings()
  const query = useQuery(getListTeamMembersQueryOptions(team.id))

  let body
  if (query.isPending) body = <SectionSkeleton rows={4} />
  else if (query.isError) body = <SectionError message={OFFLINE} onRetry={() => void query.refetch()} />
  else {
    const response = query.data
    switch (response.status) {
      case 200:
        body = <MembersView team={team} members={response.data} canEdit={canEdit} />
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
        body = <SectionError message={unexpectedStatusMessage(response)} onRetry={() => void query.refetch()} />
    }
  }

  return (
    <Section
      title="Members"
      description="Leads manage the team. Members work with its alerts and configuration. Viewers can only look."
    >
      {body}
    </Section>
  )
}

/** Refreshes what a membership change affects: the member list and, for the user's own role, `GET /me`. */
function useMembershipChanged(team: TeamRead) {
  const queryClient = useQueryClient()
  const router = useRouter()
  const { me } = useTeamSettings()
  return async (userId: string) => {
    await queryClient.invalidateQueries({ queryKey: getListTeamMembersQueryKey(team.id) })
    if (userId === me.user.id) {
      await queryClient.invalidateQueries({ queryKey: meQueryOptions.queryKey })
      await router.invalidate()
    }
  }
}

interface MembersViewProps {
  team: TeamRead
  members: MemberRead[]
  canEdit: boolean
}

function MembersView({ team, members, canEdit }: MembersViewProps) {
  const [error, setError] = useState<string | null>(null)
  const [pendingUserId, setPendingUserId] = useState<string | null>(null)
  const [removing, setRemoving] = useState<MemberRead | null>(null)
  const changed = useMembershipChanged(team)
  const setMember = useSetTeamMember()

  const changeRole = async (member: MemberRead, role: TeamRole) => {
    setError(null)
    setPendingUserId(member.user.id)
    const response = await setMember
      .mutateAsync({ teamId: team.id, userId: member.user.id, data: { role } })
      .catch(() => null)
    setPendingUserId(null)
    if (response === null) {
      setError(OFFLINE)
      return
    }
    switch (response.status) {
      case 200:
        await changed(member.user.id)
        toast.success(`${member.user.display_name} is now a ${roleLabel[role].toLowerCase()}`)
        return
      case 400:
        setError(SAVE_REJECTED)
        return
      case 401:
        return
      case 403:
        setError(SAVE_FORBIDDEN)
        return
      case 404:
        setError(`Couldn't change the role. ${member.user.display_name} is no longer in this team.`)
        await changed(member.user.id)
        return
      case 422:
        setError(bodyIssues(response.data)[0]?.message ?? SAVE_REJECTED)
        return
      default:
        setError(unexpectedStatusMessage(response))
    }
  }

  const lastLeadNoteId = 'last-lead-note'
  const showLastLeadNote = canEdit && members.some((member) => isLastLead(member, members))

  return (
    <div className="flex flex-col gap-6">
      {canEdit && <AddMember team={team} members={members} />}
      {error !== null && <FormError>{error}</FormError>}
      {members.length === 0 ? (
        <p className="text-muted-foreground">No one is in this team yet.</p>
      ) : (
        <table className="w-full border-collapse text-left">
          <thead className="text-[12px]/[16px] font-medium text-muted-foreground">
            <tr className="border-b">
              <th scope="col" className="py-2 pr-4 font-medium">
                Name
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                Email
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                Role
              </th>
              {canEdit && (
                <th scope="col" className="py-2 font-medium">
                  <span className="sr-only">Actions</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {members.map((member) => {
              const locked = isLastLead(member, members)
              const busy = pendingUserId === member.user.id
              return (
                <tr key={member.user.id} className="border-b">
                  <td className="py-2 pr-4 font-medium">{member.user.display_name}</td>
                  <td className="py-2 pr-4 font-mono text-[13px]/[20px] text-muted-foreground">
                    {member.user.email}
                  </td>
                  <td className="py-2 pr-4">
                    {canEdit ? (
                      <Select
                        items={roleItems}
                        value={member.role}
                        disabled={locked || busy}
                        onValueChange={(role) => {
                          if (role !== null && role !== member.role) void changeRole(member, role)
                        }}
                      >
                        <SelectTrigger
                          className="w-32"
                          aria-label={`Role of ${member.user.display_name}`}
                          aria-describedby={locked ? lastLeadNoteId : undefined}
                        >
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
                    ) : (
                      roleLabel[member.role]
                    )}
                  </td>
                  {canEdit && (
                    <td className="py-2 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={locked || busy}
                        aria-describedby={locked ? lastLeadNoteId : undefined}
                        aria-label={`Remove ${member.user.display_name}`}
                        onClick={() => setRemoving(member)}
                      >
                        Remove
                      </Button>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {showLastLeadNote && (
        <p id={lastLeadNoteId} className="text-[12px]/[16px] text-muted-foreground">
          {LAST_LEAD_NOTE}
        </p>
      )}
      <RemoveMemberDialog team={team} member={removing} onClose={() => setRemoving(null)} />
    </div>
  )
}

interface RemoveMemberDialogProps {
  team: TeamRead
  /** The member to remove; `null` keeps the dialog closed. */
  member: MemberRead | null
  onClose: () => void
}

function RemoveMemberDialog({ team, member, onClose }: RemoveMemberDialogProps) {
  const [error, setError] = useState<string | null>(null)
  const changed = useMembershipChanged(team)
  const remove = useRemoveTeamMember()

  const close = () => {
    setError(null)
    onClose()
  }

  const confirm = async (target: MemberRead) => {
    setError(null)
    const response = await remove.mutateAsync({ teamId: team.id, userId: target.user.id }).catch(() => null)
    if (response === null) {
      setError(OFFLINE)
      return
    }
    switch (response.status) {
      case 204:
        close()
        await changed(target.user.id)
        toast.success(`${target.user.display_name} removed from ${team.name}`)
        return
      case 401:
        return
      case 403:
        setError(SAVE_FORBIDDEN)
        return
      case 404:
        close()
        await changed(target.user.id)
        return
      case 409:
        setError(`Couldn't remove ${target.user.display_name}. ${response.data.detail}`)
        return
      case 422:
        setError(SAVE_REJECTED)
        return
      default:
        setError(unexpectedStatusMessage(response))
    }
  }

  return (
    <Dialog open={member !== null} onOpenChange={(open) => !open && close()}>
      {member !== null && (
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Remove {member.user.display_name} from {team.name}?
            </DialogTitle>
            <DialogDescription>
              They stop seeing the team's alerts and settings. You can add them again later.
            </DialogDescription>
          </DialogHeader>
          {error !== null && <FormError>{error}</FormError>}
          <DialogFooter>
            <DialogClose render={<Button variant="secondary" />}>Cancel</DialogClose>
            <Button variant="destructive" disabled={remove.isPending} onClick={() => void confirm(member)}>
              {remove.isPending ? 'Removing…' : 'Remove member'}
            </Button>
          </DialogFooter>
        </DialogContent>
      )}
    </Dialog>
  )
}

interface AddMemberProps {
  team: TeamRead
  members: MemberRead[]
}

function AddMember({ team, members }: AddMemberProps) {
  const [opened, setOpened] = useState(false)
  const [userId, setUserId] = useState<string | null>(null)
  const [role, setRole] = useState<TeamRole>('member')
  const [error, setError] = useState<string | null>(null)
  const changed = useMembershipChanged(team)
  const setMember = useSetTeamMember()
  // Loaded on first open, so readers and a lead who never adds anyone send no request.
  const users = useQuery({ ...getListUsersQueryOptions({ limit: USERS_PAGE_LIMIT }), enabled: opened })

  const memberIds = new Set(members.map((member) => member.user.id))
  let candidates: UserRead[] = []
  let empty = 'No one else to add.'
  if (users.isPending) empty = 'Loading people…'
  else if (users.isError) empty = OFFLINE
  else {
    const response = users.data
    switch (response.status) {
      case 200:
        candidates = response.data.filter((user) => !memberIds.has(user.id))
        empty = candidates.length === 0 ? 'Everyone is already in this team.' : 'No one matches.'
        break
      case 401:
        break
      case 422:
        empty = "Couldn't load people. Reload the page and try again."
        break
      default:
        empty = unexpectedStatusMessage(response)
    }
  }
  const byId = new Map(candidates.map((user) => [user.id, user]))

  const add = async () => {
    if (userId === null) {
      setError('Pick a person to add.')
      return
    }
    const user = byId.get(userId)
    setError(null)
    const response = await setMember.mutateAsync({ teamId: team.id, userId, data: { role } }).catch(() => null)
    if (response === null) {
      setError(OFFLINE)
      return
    }
    switch (response.status) {
      case 200:
        setUserId(null)
        setRole('member')
        await changed(userId)
        toast.success(`${user?.display_name ?? response.data.user.display_name} added as a ${roleLabel[role].toLowerCase()}`)
        return
      case 400:
        setError(SAVE_REJECTED)
        return
      case 401:
        return
      case 403:
        setError(SAVE_FORBIDDEN)
        return
      case 404:
        setError("Couldn't add this person. They no longer have an account.")
        return
      case 422:
        setError(bodyIssues(response.data)[0]?.message ?? SAVE_REJECTED)
        return
      default:
        setError(unexpectedStatusMessage(response))
    }
  }

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        void add()
      }}
      className="flex flex-col gap-2"
    >
      <div className="flex flex-wrap items-end gap-3">
        <Field className="w-full max-w-[320px]" invalid={error !== null && userId === null}>
          <FieldLabel>Add a person</FieldLabel>
          <Combobox
            items={candidates.map((user) => user.id)}
            value={userId}
            onValueChange={(next) => setUserId(next)}
            onOpenChange={(open) => open && setOpened(true)}
            itemToStringLabel={(id) => byId.get(id)?.display_name ?? ''}
            filter={(id, query) => {
              const user = byId.get(id)
              const needle = query.trim().toLowerCase()
              return (
                user !== undefined &&
                (user.display_name.toLowerCase().includes(needle) || user.email.toLowerCase().includes(needle))
              )
            }}
          >
            <ComboboxInput placeholder="Search by name or email" />
            <ComboboxContent empty={empty}>
              {(id: string) => {
                const user = byId.get(id)
                return (
                  <ComboboxItem key={id} value={id}>
                    <span className="truncate">{user?.display_name}</span>
                    <span className="truncate text-[12px]/[16px] text-muted-foreground">{user?.email}</span>
                  </ComboboxItem>
                )
              }}
            </ComboboxContent>
          </Combobox>
        </Field>
        <Field className="w-auto">
          <FieldLabel>Role</FieldLabel>
          <Select items={roleItems} value={role} onValueChange={(next) => next !== null && setRole(next)}>
            <SelectTrigger className="w-32">
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
        </Field>
        <Button type="submit" disabled={setMember.isPending}>
          {setMember.isPending ? 'Adding…' : 'Add member'}
        </Button>
      </div>
      {error !== null && <FormError>{error}</FormError>}
    </form>
  )
}
