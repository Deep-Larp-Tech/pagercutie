import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { ChannelPreferences } from '@/api/generated/model'
import {
  getGetUserChannelPreferencesQueryKey,
  getGetUserChannelPreferencesQueryOptions,
  useSetUserChannelPreferences,
} from '@/api/generated/users/users'
import { PageHeader } from '@/components/shell/page-header'
import { OFFLINE, LOAD_REJECTED, SAVE_REJECTED } from '@/components/team-settings/messages'
import { SectionError, SectionSkeleton } from '@/components/team-settings/section'
import { unexpectedStatusMessage } from '@/lib/api'
import { useMe } from '@/lib/session'
import { bodyIssues } from '@/lib/validation-errors'
import { ChannelPreferencesEditor, type PreferencesSaveResult } from './channel-preferences-editor'

const NOT_YOURS = 'You can only change your own notifications.'
const ACCOUNT_GONE = 'Your account no longer exists. Sign out and ask an admin to add you again.'

/** `/me/notifications`: the signed-in user's channel preferences (`DEL-2`, `DEL-3`), used when a rule routes to them. */
export function MyNotifications() {
  const { user } = useMe()
  const queryClient = useQueryClient()
  const query = useQuery(getGetUserChannelPreferencesQueryOptions(user.id))
  const save = useSetUserChannelPreferences()

  const onSave = async (preferences: ChannelPreferences): Promise<PreferencesSaveResult> => {
    const response = await save.mutateAsync({ userId: user.id, data: preferences }).catch(() => null)
    if (response === null) return { kind: 'failed', message: OFFLINE }
    switch (response.status) {
      case 200:
        queryClient.setQueryData(getGetUserChannelPreferencesQueryKey(user.id), response)
        return { kind: 'saved', preferences: response.data }
      case 400:
        return { kind: 'failed', message: SAVE_REJECTED }
      case 401:
        return { kind: 'failed', message: 'Your session ended. Sign in again to save.' }
      case 403:
        return { kind: 'failed', message: NOT_YOURS }
      case 404:
        return { kind: 'failed', message: ACCOUNT_GONE }
      case 422:
        return { kind: 'invalid', issues: bodyIssues(response.data) }
      default:
        return { kind: 'failed', message: unexpectedStatusMessage(response) }
    }
  }

  let body
  if (query.isPending) body = <SectionSkeleton rows={3} />
  else if (query.isError) body = <SectionError message={OFFLINE} onRetry={() => void query.refetch()} />
  else {
    const response = query.data
    switch (response.status) {
      case 200:
        body = <ChannelPreferencesEditor value={response.data} readOnly={false} onSave={onSave} />
        break
      case 401:
        body = null
        break
      case 403:
        body = <SectionError message={NOT_YOURS} />
        break
      case 404:
        body = <SectionError message={ACCOUNT_GONE} />
        break
      case 422:
        body = <SectionError message={LOAD_REJECTED} />
        break
      default:
        body = <SectionError message={unexpectedStatusMessage(response)} onRetry={() => void query.refetch()} />
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Notifications"
        description="How alerts reach you when a rule sends them to you. The first matching rule wins."
      />
      {body}
    </div>
  )
}
