import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'

/** Retries for a failed query; covers network errors only. */
const MAX_RETRIES = 2

declare module '@tanstack/react-query' {
  interface Register {
    queryMeta: {
      /** The query handles its own `401` (the session check in the route guards); skips `onUnauthorized`. */
      handlesUnauthorized?: boolean
    }
  }
}

/** Options for `createQueryClient`. */
export interface QueryClientOptions {
  /** Called when a query or mutation answers `401`: the session ended, so the user must sign in again. */
  onUnauthorized?: () => void
}

/** Whether a generated client response (`{ status, data }`) carries the status `401`. */
export function isUnauthorized(response: unknown): boolean {
  return (
    typeof response === 'object' && response !== null && 'status' in response && response.status === 401
  )
}

/**
 * Creates the app's QueryClient. The generated fetch client resolves every HTTP status as `{ data, status }`
 * instead of throwing, so 4xx and 5xx answers never reach `retry`; only network and parse errors do. For the same
 * reason a `401` arrives in the caches' `onSuccess`, which calls `onUnauthorized` (ADR-0048).
 */
export function createQueryClient({ onUnauthorized }: QueryClientOptions = {}) {
  return new QueryClient({
    queryCache: new QueryCache({
      onSuccess: (data, query) => {
        if (isUnauthorized(data) && !query.meta?.handlesUnauthorized) onUnauthorized?.()
      },
    }),
    mutationCache: new MutationCache({
      onSuccess: (data) => {
        if (isUnauthorized(data)) onUnauthorized?.()
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount) => failureCount < MAX_RETRIES,
      },
    },
  })
}
