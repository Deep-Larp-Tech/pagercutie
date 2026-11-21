import { http, HttpResponse } from 'msw'

/** HTTP methods the management API uses. */
export type Method = 'get' | 'post' | 'put' | 'patch' | 'delete'

/** A generated fetch function, e.g. `getMe` or `deleteTeam`; it resolves to `{ status, data }` for every status. */
type Operation = (...args: never[]) => Promise<{ status: number; data: unknown }>

type OperationResponse<Op extends Operation> = Awaited<ReturnType<Op>>

/** Statuses the OpenAPI contract documents for an operation. */
export type ResponseStatus<Op extends Operation> = OperationResponse<Op>['status']

/** Body the contract documents for an operation at one status; `void` for empty responses. */
export type ResponseBody<Op extends Operation, S extends ResponseStatus<Op>> = Extract<
  OperationResponse<Op>,
  { status: S }
>['data']

/**
 * MSW handler that answers one endpoint with `status` and `body`, for `server.use(...)` in a test.
 *
 * `operation` is the generated fetch function and is used only for its type: it limits `status` to the statuses
 * the contract documents and types `body` for that status. Build `url` with the generated URL helper, e.g.
 * `respond(getMe, 'get', getGetMeUrl(), 401, { detail: 'Sign in again.' })` or
 * `respond(deleteTeam, 'delete', getDeleteTeamUrl(teamId), 204, undefined)`.
 * The query string is dropped because MSW matches on the path only.
 */
export function respond<Op extends Operation, S extends ResponseStatus<Op>>(
  _operation: Op,
  method: Method,
  url: string,
  status: S,
  body: ResponseBody<Op, S>,
) {
  const [path] = url.split('?')
  return http[method](path, () =>
    body === undefined
      ? new HttpResponse(null, { status })
      : new HttpResponse(JSON.stringify(body), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
  )
}
