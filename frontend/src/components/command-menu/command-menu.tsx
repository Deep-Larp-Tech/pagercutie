import { useEffect, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Command } from 'cmdk'
import {
  Bell,
  BellRing,
  BookOpen,
  Check,
  CheckCheck,
  Hand,
  History,
  LayoutDashboard,
  ListFilter,
  Monitor,
  Moon,
  Plug,
  Search,
  Settings,
  Sun,
  UserRound,
  UsersRound,
  type LucideIcon,
} from 'lucide-react'
import {
  getListAlertsQueryKey,
  getListAlertsQueryOptions,
  type listAlertsResponse,
} from '@/api/generated/alerts/alerts'
import { AlertStatus, type AlertRead, type ListAlertsParams } from '@/api/generated/model'
import { getListRulesQueryOptions } from '@/api/generated/rules/rules'
import { getListRunbooksQueryOptions } from '@/api/generated/runbooks/runbooks'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { useAlertResponse } from '@/hooks/use-alert-response'
import { ALERTS_PAGE_LIMIT } from '@/hooks/use-alert-stream'
import { useVisibleTeams } from '@/hooks/use-visible-teams'
import { can } from '@/lib/permissions'
import { useMe } from '@/lib/session'
import { alertColourClass, severityIcon, severityLabel } from '@/lib/severity'
import { applyTheme, readThemeChoice, storeThemeChoice, themeChoices, type ThemeChoice } from '@/lib/theme'
import { cn } from '@/lib/utils'
import { groupState, isApplePlatform, matches, type GroupState } from './search'

/** Same parameters as the Overview feed, so the menu reads the cache entry the Overview keeps live. */
const OPEN_ALERTS_PARAMS = {
  limit: ALERTS_PAGE_LIMIT,
  status: [AlertStatus.open, AlertStatus.acknowledged],
} as const satisfies ListAlertsParams

/** Alerts, rules and runbooks shown per group while the search is empty; typing searches the whole list. */
const IDLE_LIMIT = 5

const icon = { strokeWidth: 1.75, 'aria-hidden': true } as const

const themeAction = {
  light: { label: 'Switch to light theme', icon: Sun },
  dark: { label: 'Switch to dark theme', icon: Moon },
  system: { label: 'Use the system theme', icon: Monitor },
} as const satisfies Record<ThemeChoice, { label: string; icon: LucideIcon }>

const itemClass = cn(
  'relative flex min-h-9 cursor-default items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm outline-none select-none',
  'data-[selected=true]:bg-accent data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50',
  '[&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground',
)

const groupClass =
  'px-1 pb-2 [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[12px]/[16px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground'

/** A destination in the Navigate group. */
interface Destination {
  id: string
  label: string
  /** Sidebar section or team name, shown muted after the label and searched with it. */
  section: string
  icon: LucideIcon
  go: () => void
}

/**
 * `⌘K` / `Ctrl K` command menu (DESIGN.md §9): jump to a page, an open alert, a rule or a runbook of the current team,
 * acknowledge or resolve the highlighted alert, or switch the theme. The trigger in the header shows the shortcut.
 */
export function CommandMenu() {
  const [open, setOpen] = useState(false)
  const apple = isApplePlatform()

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey) || event.altKey || event.shiftKey) return
      // Browsers bind Ctrl K and ⌘K to their own search box.
      event.preventDefault()
      setOpen((current) => !current)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button
            variant="secondary"
            aria-label="Search"
            aria-keyshortcuts={apple ? 'Meta+K' : 'Control+K'}
            className="text-muted-foreground"
          />
        }
      >
        <Search strokeWidth={1.75} />
        <span className="hidden sm:inline">Search</span>
        <kbd aria-hidden className="hidden rounded-sm bg-muted px-1.5 font-mono text-[12px]/[16px] sm:inline">
          {apple ? '⌘K' : 'Ctrl K'}
        </kbd>
      </DialogTrigger>
      <DialogContent
        showCloseButton={false}
        className="top-[12vh] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-xl"
      >
        <DialogTitle className="sr-only">Search and commands</DialogTitle>
        {open && <CommandPanel onClose={() => setOpen(false)} />}
      </DialogContent>
    </Dialog>
  )
}

/** Alerts the menu knows about, from the Overview's `GET /alerts` entry and every other cached feed. */
interface KnownAlerts {
  /** Open and acknowledged alerts, most recently seen first. */
  state: GroupState<AlertRead>
  /** Every cached alert by id, resolved ones included, so a resolved target still shows its current state. */
  byId: ReadonlyMap<string, AlertRead>
}

function useKnownAlerts(): KnownAlerts {
  const queryClient = useQueryClient()
  const query = useQuery(getListAlertsQueryOptions(OPEN_ALERTS_PARAMS))
  const own = groupState(query.data, query.isError)
  // Read on every render: the query above re-renders this hook whenever a response changes any cached feed, since
  // Acknowledge, Resolve and the stream update every `GET /alerts` entry together.
  const byId = new Map<string, AlertRead>()
  if (own.kind === 'listed') for (const alert of own.items) byId.set(alert.id, alert)
  for (const [, response] of queryClient.getQueriesData<listAlertsResponse>({ queryKey: getListAlertsQueryKey() })) {
    if (response?.status !== 200) continue
    for (const alert of response.data) if (!byId.has(alert.id)) byId.set(alert.id, alert)
  }
  const items = [...byId.values()]
    .filter((alert) => alert.status !== AlertStatus.resolved)
    .toSorted((a, b) => b.last_seen_at.localeCompare(a.last_seen_at))
  const state = own.kind !== 'listed' && items.length === 0 ? own : { kind: 'listed' as const, items }
  return { state, byId }
}

function CommandPanel({ onClose }: { onClose: () => void }) {
  const me = useMe()
  const navigate = useNavigate()
  const { teams, current } = useVisibleTeams()
  const [search, setSearch] = useState('')
  const [themeChoice, setThemeChoice] = useState(readThemeChoice)
  const { state: alerts, byId: knownAlerts } = useKnownAlerts()
  const teamId = current?.team.id
  const rulesQuery = useQuery({
    ...getListRulesQueryOptions({ team_id: teamId, limit: ALERTS_PAGE_LIMIT }),
    enabled: teamId !== undefined,
  })
  const runbooksQuery = useQuery({
    ...getListRunbooksQueryOptions({ team_id: teamId, limit: ALERTS_PAGE_LIMIT }),
    enabled: teamId !== undefined,
  })

  // The alert whose actions show under it: the last alert the highlight was on, kept while the highlight moves onto
  // its actions. A snapshot stands in once a resolve takes it out of the open list, so an error can still show.
  const [target, setTarget] = useState<AlertRead | null>(null)
  // Controlled, because cmdk reports highlight changes (including its own pick of the first item) only then.
  const [highlighted, setHighlighted] = useState('')
  const listed = alerts.kind === 'listed' ? alerts.items : []
  const latestTarget = target === null ? undefined : knownAlerts.get(target.id)
  if (latestTarget !== undefined && latestTarget !== target) setTarget(latestTarget)
  const targetAlert = latestTarget ?? target

  const run = (action: () => void) => {
    action()
    onClose()
  }

  const teamName = (alert: AlertRead) =>
    alert.team_id === null ? 'Personal rule' : teams.find(({ team }) => team.id === alert.team_id)?.team.name

  const openAlert = (alert: AlertRead) => {
    // There is no alert detail route yet; the team's feed filtered to the alert's status and severity stands in.
    const team = [alert.team_id, ...alert.escalated_team_ids]
      .map((id) => teams.find((visible) => visible.team.id === id))
      .find((visible) => visible !== undefined)
    run(() =>
      team === undefined
        ? void navigate({ to: '/' })
        : void navigate({
            to: '/teams/$team/alerts',
            params: { team: team.team.slug },
            search: { status: [alert.status], severity: [alert.severity] },
          }),
    )
  }

  const destinations: Destination[] = [
    { id: 'overview', label: 'Overview', section: 'Pages', icon: LayoutDashboard, go: () => void navigate({ to: '/' }) },
  ]
  if (current !== undefined && can(me, 'team.read', current.team.id)) {
    const params = { team: current.team.slug }
    const section = current.team.name
    destinations.push(
      { id: 'team-alerts', label: 'Alerts', section, icon: Bell, go: () => void navigate({ to: '/teams/$team/alerts', params }) },
      { id: 'team-rules', label: 'Rules', section, icon: ListFilter, go: () => void navigate({ to: '/teams/$team/rules', params }) },
      { id: 'team-runbooks', label: 'Runbooks', section, icon: BookOpen, go: () => void navigate({ to: '/teams/$team/runbooks', params }) },
      { id: 'team-sources', label: 'Sources', section, icon: Plug, go: () => void navigate({ to: '/teams/$team/sources', params }) },
      { id: 'team-settings', label: 'Settings', section, icon: Settings, go: () => void navigate({ to: '/teams/$team/settings', params }) },
    )
    if (can(me, 'audit.read', current.team.id)) {
      destinations.push({
        id: 'team-audit',
        label: 'Audit log',
        section,
        icon: History,
        go: () => void navigate({ to: '/teams/$team/audit', params }),
      })
    }
  }
  for (const { team } of teams) {
    if (team.id === current?.team.id) continue
    destinations.push({
      id: `switch-${team.id}`,
      label: `Switch to ${team.name}`,
      section: 'Teams',
      icon: UsersRound,
      go: () => void navigate({ to: '/teams/$team/alerts', params: { team: team.slug } }),
    })
  }
  destinations.push(
    { id: 'my-rules', label: 'My rules', section: 'Me', icon: ListFilter, go: () => void navigate({ to: '/me/rules' }) },
    { id: 'my-notifications', label: 'Notifications', section: 'Me', icon: BellRing, go: () => void navigate({ to: '/me/notifications' }) },
    { id: 'my-profile', label: 'Profile', section: 'Me', icon: UserRound, go: () => void navigate({ to: '/me/profile' }) },
  )
  if (can(me, 'users-and-teams.manage')) {
    destinations.push(
      { id: 'admin-users', label: 'Users', section: 'Admin', icon: UserRound, go: () => void navigate({ to: '/admin/users' }) },
      { id: 'admin-teams', label: 'Teams', section: 'Admin', icon: UsersRound, go: () => void navigate({ to: '/admin/teams' }) },
      { id: 'admin-audit', label: 'Audit log', section: 'Admin', icon: History, go: () => void navigate({ to: '/admin/audit' }) },
    )
  }

  const idle = search.trim() === ''
  const shownDestinations = destinations.filter((entry) => matches(search, entry.label, entry.section))
  const shownAlerts = listed
    .filter((alert) => matches(search, alert.title, alert.fingerprint, teamName(alert), severityLabel[alert.severity]))
    .slice(0, idle ? IDLE_LIMIT : undefined)
  // A target that a resolve removed from the list keeps its row until the menu closes.
  if (targetAlert !== null && !shownAlerts.some((alert) => alert.id === targetAlert.id) && targetAlert.status === 'resolved') {
    shownAlerts.push(targetAlert)
  }
  const themes = themeChoices.filter(
    (choice) => choice !== themeChoice && matches(search, themeAction[choice].label, 'theme'),
  )
  const rules = groupState(rulesQuery.data, rulesQuery.isError)
  const runbooks = groupState(runbooksQuery.data, runbooksQuery.isError)
  const matchedRules = rules.kind === 'listed' ? rules.items.filter((rule) => matches(search, rule.name, rule.description)) : []
  const matchedRunbooks =
    runbooks.kind === 'listed' ? runbooks.items.filter((runbook) => matches(search, runbook.title, runbook.slug)) : []

  return (
    <Command
      label="Search and commands"
      shouldFilter={false}
      loop
      value={highlighted}
      onValueChange={(value) => {
        setHighlighted(value)
        if (!value.startsWith('alert:')) return
        const alert = listed.find((item) => `alert:${item.id}` === value)
        if (alert !== undefined) setTarget(alert)
      }}
      className="flex flex-col"
    >
      <div className="flex items-center gap-2 border-b px-4">
        <Search {...icon} className="size-4 shrink-0 text-muted-foreground" />
        <Command.Input
          value={search}
          onValueChange={setSearch}
          placeholder="Search pages, alerts, rules and runbooks"
          className="h-12 w-full min-w-0 bg-transparent text-[15px]/[22px] outline-none placeholder:text-muted-foreground"
        />
      </div>
      <Command.List className="max-h-[min(60vh,440px)] scroll-py-2 overflow-y-auto py-1">
        <Command.Empty className="px-4 py-8 text-center text-muted-foreground">
          Nothing matches “{search.trim()}”.
        </Command.Empty>

        <ListGroup heading="Alerts" state={alerts} shown={shownAlerts.length} search={search} noun="open alerts">
          {shownAlerts.map((alert) => (
            <AlertEntry
              key={alert.id}
              alert={alert}
              teamName={teamName(alert)}
              onOpen={() => openAlert(alert)}
              actions={targetAlert?.id === alert.id ? <AlertActions key={alert.id} alert={targetAlert} /> : null}
            />
          ))}
        </ListGroup>

        {shownDestinations.length > 0 && (
          <Command.Group heading="Navigate" className={groupClass}>
            {shownDestinations.map((entry) => (
              <Command.Item key={entry.id} value={`page:${entry.id}`} onSelect={() => run(entry.go)} className={itemClass}>
                <entry.icon {...icon} />
                <span className="truncate">{entry.label}</span>
                <span className="ml-auto truncate text-[12px]/[16px] text-muted-foreground">{entry.section}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

        {current !== undefined && (
          <ListGroup
            heading={`Rules in ${current.team.name}`}
            state={rules}
            shown={matchedRules.length}
            search={search}
            noun="rules"
          >
            {matchedRules.slice(0, idle ? IDLE_LIMIT : undefined).map((rule) => (
                  <Command.Item
                    key={rule.id}
                    value={`rule:${rule.id}`}
                    onSelect={() =>
                      run(() => void navigate({ to: '/teams/$team/rules', params: { team: current.team.slug } }))
                    }
                    className={itemClass}
                  >
                    <ListFilter {...icon} />
                    <span className="truncate">{rule.name}</span>
                    {!rule.enabled && <span className="ml-auto text-[12px]/[16px] text-muted-foreground">Off</span>}
                  </Command.Item>
                ))}
          </ListGroup>
        )}

        {current !== undefined && (
          <ListGroup
            heading={`Runbooks in ${current.team.name}`}
            state={runbooks}
            shown={matchedRunbooks.length}
            search={search}
            noun="runbooks"
          >
            {matchedRunbooks.slice(0, idle ? IDLE_LIMIT : undefined).map((runbook) => (
                  <Command.Item
                    key={runbook.id}
                    value={`runbook:${runbook.id}`}
                    onSelect={() =>
                      run(() => void navigate({ to: '/teams/$team/runbooks', params: { team: current.team.slug } }))
                    }
                    className={itemClass}
                  >
                    <BookOpen {...icon} />
                    <span className="truncate">{runbook.title}</span>
                    <span className="ml-auto truncate font-mono text-[12px]/[16px] text-muted-foreground">
                      {runbook.slug}
                    </span>
                  </Command.Item>
                ))}
          </ListGroup>
        )}

        {themes.length > 0 && (
          <Command.Group heading="Actions" className={groupClass}>
            {themes.map((choice) => {
              const { label, icon: ThemeIcon } = themeAction[choice]
              return (
                <Command.Item
                  key={choice}
                  value={`theme:${choice}`}
                  onSelect={() => {
                    storeThemeChoice(choice)
                    applyTheme(choice)
                    setThemeChoice(choice)
                  }}
                  className={itemClass}
                >
                  <ThemeIcon {...icon} />
                  {label}
                </Command.Item>
              )
            })}
          </Command.Group>
        )}
      </Command.List>
      <p className="flex gap-4 border-t px-4 py-2 text-[12px]/[16px] text-muted-foreground" aria-hidden>
        <span>↑ ↓ to move</span>
        <span>Enter to open</span>
        <span>Esc to close</span>
      </p>
    </Command>
  )
}

/** Props for `ListGroup`. */
interface ListGroupProps {
  heading: string
  state: GroupState<unknown>
  /** How many entries match the search. */
  shown: number
  search: string
  /** Plural noun for the "no match" and "nothing to offer" lines, e.g. "rules". */
  noun: string
  children: ReactNode
}

/** A searched group: its entries, or one muted line while loading, on failure, with no match or nothing to offer. */
function ListGroup({ heading, state, shown, search, noun, children }: ListGroupProps) {
  if (state.kind === 'silent') return null
  let line: string | null = null
  if (state.kind === 'loading') line = `Loading ${noun}…`
  else if (state.kind === 'failed') line = state.message
  else if (state.items.length === 0 && search.trim() === '') line = `No ${noun}.`
  // A group with nothing to say while the user searches stays out of the way of the results.
  if (line === null && shown === 0) return null
  return (
    <Command.Group heading={heading} forceMount className={groupClass}>
      {line !== null ? <p className="px-2.5 py-1.5 text-muted-foreground">{line}</p> : children}
    </Command.Group>
  )
}

/** Props for `AlertEntry`. */
interface AlertEntryProps {
  alert: AlertRead
  /** Owning team's name, "Personal rule", or `undefined` for a team the user cannot open. */
  teamName: string | undefined
  onOpen: () => void
  /** Acknowledge and Resolve, rendered right under the highlighted alert so the keyboard reaches them next. */
  actions: ReactNode
}

function AlertEntry({ alert, teamName, onOpen, actions }: AlertEntryProps) {
  const SeverityIcon = severityIcon[alert.severity]
  return (
    <>
      <Command.Item
        value={`alert:${alert.id}`}
        onSelect={onOpen}
        disabled={alert.status === 'resolved'}
        className={cn(itemClass, alertColourClass[alert.colour])}
      >
        <SeverityIcon {...icon} className="text-c-text!" />
        <span className="sr-only">{severityLabel[alert.severity]}:</span>
        <span className={cn('truncate', alert.status === 'resolved' && 'text-muted-foreground line-through')}>
          {alert.title}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-2 text-[12px]/[16px] text-muted-foreground">
          {alert.status === 'acknowledged' && <span>Acknowledged</span>}
          {alert.status === 'resolved' && <span>Resolved</span>}
          {teamName !== undefined && <span className="max-w-32 truncate">{teamName}</span>}
        </span>
      </Command.Item>
      {actions}
    </>
  )
}

/** Acknowledge and Resolve for one alert, for users who may respond; the outcome shows inline and as a toast. */
function AlertActions({ alert }: { alert: AlertRead }) {
  const me = useMe()
  const { acknowledge, resolve, error } = useAlertResponse(alert)
  // A personal rule's alert (no team) is visible to its owner, who may respond; `can` leaves that call to us.
  const mayRespond = alert.team_id === null || can(me, 'alert.respond', alert)
  if (!mayRespond) return null
  return (
    <div className="flex flex-col gap-0.5 pb-1 pl-6">
      {alert.status === 'open' && (
        <Command.Item value={`respond:${alert.id}:acknowledge`} onSelect={acknowledge} className={itemClass}>
          <Hand {...icon} />
          Acknowledge
          <span className="ml-auto text-[12px]/[16px] text-muted-foreground">Tell your team you are on it</span>
        </Command.Item>
      )}
      {alert.status !== 'resolved' && (
        <Command.Item value={`respond:${alert.id}:resolve`} onSelect={resolve} className={itemClass}>
          <CheckCheck {...icon} />
          Resolve
          <span className="ml-auto text-[12px]/[16px] text-muted-foreground">Mark the problem as fixed</span>
        </Command.Item>
      )}
      {alert.status === 'resolved' && error === null && (
        <p className="flex items-center gap-2 px-2.5 py-1.5 text-muted-foreground">
          <Check {...icon} className="size-4" />
          Resolved
        </p>
      )}
      {error !== null && (
        <p role="alert" className="px-2.5 py-1.5 text-[12px]/[16px] font-medium text-alert-red-text">
          {error}
        </p>
      )}
    </div>
  )
}
