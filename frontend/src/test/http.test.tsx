import { describe, expect, expectTypeOf, test } from 'vitest'
import { getGetMeUrl, getMe, useGetMe } from '@/api/generated/auth/auth'
import { getGetMeResponseMock } from '@/api/generated/auth/auth.faker'
import { respond, type ResponseBody, type ResponseStatus } from './http'
import { renderWithProviders } from './render'
import { server } from './server'

function CurrentUser() {
  const { data } = useGetMe()
  if (!data) return <p>Loading</p>
  switch (data.status) {
    case 200:
      return <p>Signed in as {data.data.user.display_name}</p>
    case 401:
      return <p role="alert">{data.data.detail}</p>
    default:
      return data satisfies never
  }
}

describe('respond', () => {
  test('answers with the success body', async () => {
    const me = getGetMeResponseMock({})
    server.use(respond(getMe, 'get', getGetMeUrl(), 200, me))

    const { findByText } = renderWithProviders(<CurrentUser />)

    expect(await findByText(`Signed in as ${me.user.display_name}`)).toBeInTheDocument()
  })

  test('answers with an error status and its body', async () => {
    server.use(respond(getMe, 'get', getGetMeUrl(), 401, { detail: 'Sign in again.' }))

    const { findByRole } = renderWithProviders(<CurrentUser />)

    expect(await findByRole('alert')).toHaveTextContent('Sign in again.')
  })

  test('types status and body from the contract', () => {
    expectTypeOf<ResponseStatus<typeof getMe>>().toEqualTypeOf<200 | 401>()
    expectTypeOf<ResponseBody<typeof getMe, 401>>().toEqualTypeOf<{ detail: string }>()
  })
})
