import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { ChannelPreferences } from '@/api/generated/model'
import {
  getGetTeamChannelPreferencesQueryKey,
  getGetTeamChannelPreferencesQueryOptions,
  useSetTeamChannelPreferences,
} from '@/api/generated/teams/teams'
import {
  ChannelPreferencesEditor,
  type PreferencesSaveResult,
} from '@/components/preferences/channel-preferences-editor'
import { unexpectedStatusMessage } from '@/lib/api'
import { bodyIssues } from '@/lib/validation-errors'
import { LOAD_REJECTED, OFFLINE, SAVE_FORBIDDEN, SAVE_REJECTED, TEAM_GONE } from './messages'
import { Section, SectionError, SectionSkeleton } from './section'
import { useTeamSettings } from './use-team-settings'

/**
 * `/teams/$team/settings/notifications`: the team's channel preferences (`DEL-2`), used for `team` and `on_call`
 * recipients whose rule sets no channels (DOMAIN.md §5).
 */
export function NotificationSettings() {
  const { team, canEdit } = useTeamSettings()
  const queryClient = useQueryClient()
  const query = useQuery(getGetTeamChannelPreferencesQueryOptions(team.id))
  const save = useSetTeamChannelPreferences()

  const onSave = async (preferences: ChannelPreferences): Promise<PreferencesSaveResult> => {
    const response = await save.mutateAsync({ teamId: team.id, data: preferences }).catch(() => null)
    if (response === null) return { kind: 'failed', message: OFFLINE }
    switch (response.status) {
      case 200:
        queryClient.setQueryData(getGetTeamChannelPreferencesQueryKey(team.id), response)
        return { kind: 'saved', preferences: response.data }
      case 400:
        return { kind: 'failed', message: SAVE_REJECTED }
      case 401:
        return { kind: 'failed', message: 'Your session ended. Sign in again to save.' }
      case 403:
        return { kind: 'failed', message: SAVE_FORBIDDEN }
      case 404:
        return { kind: 'failed', message: TEAM_GONE }
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
        body = <ChannelPreferencesEditor value={response.data} readOnly={!canEdit} onSave={onSave} />
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
      title="Notifications"
      description="How the team hears about alerts sent to the whole team or to whoever is on call. The first matching rule wins."
    >
      {body}
    </Section>
  )
}
