import { describe, expect, test, vi } from 'vitest'
import { getGetMeUrl, getLogoutMutationOptions, getLogoutUrl, getMe, logout } from '@/api/generated/auth/auth'
import { getGetMeResponseMock } from '@/api/generated/auth/auth.faker'
import { getListTeamsQueryOptions, getListTeamsUrl, listTeams } from '@/api/generated/teams/teams'
import { respond } from '@/test/http'
import { server } from '@/test/server'
import { createQueryClient } from './query'
import { meQueryOptions } from './session'

describe('createQueryClient', () => {
  test('a query answering 401 calls onUnauthorized', async () => {
    const onUnauthorized = vi.fn()
    server.use(respond(listTeams, 'get', getListTeamsUrl(), 401, { detail: 'Not signed in.' }))

    await createQueryClient({ onUnauthorized }).fetchQuery(getListTeamsQueryOptions())

    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  test('a mutation answering 401 calls onUnauthorized', async () => {
    const onUnauthorized = vi.fn()
    server.use(respond(logout, 'post', getLogoutUrl(), 401, { detail: 'Not signed in.' }))
    const queryClient = createQueryClient({ onUnauthorized })

    await queryClient.getMutationCache().build(queryClient, getLogoutMutationOptions()).execute(undefined)

    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  test('the session query handles its own 401', async () => {
    const onUnauthorized = vi.fn()
    server.use(respond(getMe, 'get', getGetMeUrl(), 401, { detail: 'Not signed in.' }))

    await createQueryClient({ onUnauthorized }).fetchQuery(meQueryOptions)

    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  test('other statuses do not call onUnauthorized', async () => {
    const onUnauthorized = vi.fn()
    server.use(respond(getMe, 'get', getGetMeUrl(), 200, getGetMeResponseMock()))

    await createQueryClient({ onUnauthorized }).fetchQuery(meQueryOptions)

    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})
