import { onTestFinished } from 'vitest'
import type { MemberRead, MeRead, TeamRole, UserRead } from '@/api/generated/model'
import { getGetMeUrl, getMe } from '@/api/generated/auth/auth'
import { respond, type Method } from './http'
import { membership, petra, team } from './people'
import { renderApp } from './render'
import { server } from './server'

/** Team Settlements, the team every team settings test opens. */
export const settlements = team('settlements', 'Settlements')

/** A user with an id derived from `key`, e.g. `user('bob', 'Bob Novak')`. */
export function user(key: string, displayName: string): UserRead {
  return {
    id: `user-${key}`,
    email: `${key}@example.com`,
    display_name: displayName,
    phone: null,
    timezone: 'Europe/Prague',
    role: 'user',
    created_at: '2026-01-01T00:00:00Z',
  }
}

/** A `GET /teams/{id}/members` row. */
export function member(of: UserRead, role: TeamRole): MemberRead {
  return { user: of, role }
}

/** Petra with `role` in Settlements and global role `user`. */
export function petraIn(role: TeamRole): MeRead {
  return petra('user', [membership(settlements, role)])
}

/** Signs `me` in through `GET /me` and renders the real app at `path`, e.g. `/teams/settlements/settings/members`. */
export function openAs(me: MeRead, path: string) {
  server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))
  return renderApp(path)
}

/** A request the app sent during a test: its method, path and JSON body (`null` without one). */
export interface SentRequest {
  method: string
  path: string
  body: unknown
}

/**
 * Records every `method` request the app sends to `path` from now until the end of the test. Read it inside
 * `waitFor`: the body is parsed after the request starts.
 */
export function recordRequests(method: Method, path: string): SentRequest[] {
  const sent: SentRequest[] = []
  const listener = ({ request }: { request: Request }) => {
    const url = new URL(request.url)
    if (url.pathname !== path || request.method !== method.toUpperCase()) return
    const entry: SentRequest = { method: request.method, path: url.pathname, body: null }
    sent.push(entry)
    void request
      .clone()
      .text()
      .then((text) => {
        entry.body = text === '' ? null : JSON.parse(text)
      })
  }
  server.events.on('request:start', listener)
  onTestFinished(() => server.events.removeListener('request:start', listener))
  return sent
}
