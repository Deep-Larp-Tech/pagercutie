import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ListFilter, Plus } from 'lucide-react'
import type { RuleRead } from '@/api/generated/model'
import { getListRulesQueryKey, listRules, useUpdateRule, type listRulesResponse } from '@/api/generated/rules/rules'
import { FormError, ListFailed, ShowMore, SkeletonRows } from '@/components/admin/list-parts'
import { RelativeTime } from '@/components/alerts/relative-time'
import { SeverityBadge } from '@/components/alerts/severity-badge'
import { EmptyState } from '@/components/shell/empty-state'
import { PageHeader } from '@/components/shell/page-header'
import { buttonVariants } from '@/components/ui/styles'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { unexpectedStatusMessage } from '@/lib/api'
import { useOffsetPages, type PageResult } from '@/lib/pagination'
import { useMe } from '@/lib/session'
import { bodyIssues } from '@/lib/validation-errors'
import { BODY_UNREADABLE, forbiddenMessage, OFFLINE, RULE_GONE } from './messages'
import { describeRecipients } from './recipients'
import { RuleLink } from './rule-link'
import { scopeListParams, type RuleScope } from './rule-scope'
import { useRecipientNames } from './use-recipient-names'

const COLUMNS = 5

/** Reads one `GET /rules` page. */
function readRulesPage(response: listRulesResponse): PageResult<RuleRead> {
  switch (response.status) {
    case 200:
      return { kind: 'items', items: response.data }
    case 401:
      return { kind: 'silent' }
    case 422:
      return { kind: 'failed', message: 'The list request was not valid. Reload the page and try again.' }
    default:
      return { kind: 'failed', message: unexpectedStatusMessage(response) }
  }
}

/** Props for `RulesPage`. */
export interface RulesPageProps {
  scope: RuleScope
}

/**
 * `/teams/$team/rules` and `/me/rules`: the scope's rules with their state, severity and recipients (`UI-3`). Members
 * and leads (or the owner, for personal rules) switch rules on and off here and open the builder; everyone else reads.
 */
export function RulesPage({ scope }: RulesPageProps) {
  const me = useMe()
  const params = scopeListParams(scope)
  const pages = useOffsetPages(
    [...getListRulesQueryKey(params), 'pages'],
    (page, signal) => listRules({ ...params, ...page }, { signal }),
    readRulesPage,
  )
  const { list } = pages
  const rules = list.kind === 'listed' ? list.items : []
  const names = useRecipientNames(rules.some((rule) => rule.routing.recipients.some(({ type }) => type === 'user' )))
  const toggle = useEnableToggle(scope)
  const personal = scope.kind === 'personal'

  const newRule = scope.canEdit && (
    <RuleLink scope={scope} to="new" className={buttonVariants()}>
      <Plus strokeWidth={1.75} aria-hidden />
      New rule
    </RuleLink>
  )

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={personal ? 'My rules' : 'Rules'}
        description={
          personal
            ? 'Rules that alert only you, for events from the teams you belong to.'
            : `Rules decide which events of ${scope.team.name} become alerts, who hears about them and how they look.`
        }
        actions={newRule}
      />
      {!scope.canEdit && <p className="text-muted-foreground">{forbiddenMessage(scope)}</p>}
      {toggle.error !== null && <FormError>{toggle.error}</FormError>}
      {list.kind === 'failed' ? (
        <ListFailed title="Couldn't load rules" message={list.message} onRetry={pages.retry} />
      ) : list.kind === 'listed' && rules.length === 0 ? (
        <EmptyState
          icon={ListFilter}
          title="No rules yet"
          description={
            scope.canEdit
              ? 'Without rules no event becomes an alert. Add the first one with New rule.'
              : 'Without rules no event becomes an alert.'
          }
          action={newRule}
        />
      ) : (
        <Table aria-label={personal ? 'My rules' : 'Rules'} aria-busy={list.kind === 'loading'}>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>On</TableHead>
              <TableHead>Severity</TableHead>
              <TableHead>Who is notified</TableHead>
              <TableHead>Last changed</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.kind === 'loading' ? (
              <SkeletonRows columns={COLUMNS} />
            ) : (
              rules.map((rule) => {
                const enabled = toggle.pending[rule.id] ?? rule.enabled
                return (
                  <TableRow key={rule.id}>
                    <TableCell className="max-w-80">
                      <RuleLink scope={scope} to={rule.id} className="font-medium hover:underline">
                        {rule.name}
                      </RuleLink>
                      {rule.description !== null && (
                        <p className="truncate text-[12px]/[16px] text-muted-foreground">{rule.description}</p>
                      )}
                    </TableCell>
                    <TableCell>
                      {scope.canEdit ? (
                        <Switch
                          aria-label={`Rule ${rule.name} is on`}
                          checked={enabled}
                          disabled={toggle.pending[rule.id] !== undefined}
                          onCheckedChange={(checked) => void toggle.set(rule, checked)}
                        />
                      ) : (
                        <span className="text-muted-foreground">{rule.enabled ? 'On' : 'Off'}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <SeverityBadge severity={rule.presentation.severity} colour={rule.presentation.colour} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {describeRecipients(rule.routing.recipients, names)}
                    </TableCell>
                    <TableCell>
                      <RelativeTime value={rule.updated_at} timeZone={me.user.timezone} />
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      )}
      <ShowMore pages={pages} />
    </div>
  )
}

/** Switches a rule on or off with `PATCH /rules/{id} {enabled}`; the switch shows the new state while it saves. */
function useEnableToggle(scope: RuleScope) {
  const queryClient = useQueryClient()
  const update = useUpdateRule()
  const [pending, setPending] = useState<Partial<Record<string, boolean>>>({})
  const [error, setError] = useState<string | null>(null)

  const finish = async (ruleId: string) => {
    await queryClient.invalidateQueries({ queryKey: getListRulesQueryKey() })
    setPending((current) => Object.fromEntries(Object.entries(current).filter(([id]) => id !== ruleId)))
  }

  const set = async (rule: RuleRead, enabled: boolean) => {
    setError(null)
    setPending((current) => ({ ...current, [rule.id]: enabled }))
    const response = await update.mutateAsync({ ruleId: rule.id, data: { enabled } }).catch(() => null)
    const verb = enabled ? 'switch on' : 'switch off'
    if (response === null) setError(OFFLINE)
    else {
      switch (response.status) {
        case 200:
          break
        case 400:
          setError(BODY_UNREADABLE)
          break
        case 401:
          break
        case 403:
          setError(`Couldn't ${verb} ${rule.name}. ${forbiddenMessage(scope)}`)
          break
        case 404:
          setError(`Couldn't ${verb} ${rule.name}. ${RULE_GONE}`)
          break
        case 422:
          setError(`Couldn't ${verb} ${rule.name}. ${bodyIssues(response.data)[0]?.message ?? 'Try again.'}`)
          break
        default:
          setError(`Couldn't ${verb} ${rule.name}. ${unexpectedStatusMessage(response)}`)
      }
    }
    await finish(rule.id)
  }

  return { pending, error, set }
}
