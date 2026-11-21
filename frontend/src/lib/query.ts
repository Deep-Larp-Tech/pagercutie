import { QueryClient } from '@tanstack/react-query'

/** Retries for a failed query; covers network errors only. */
const MAX_RETRIES = 2

/**
 * Creates the app's QueryClient. The generated fetch client resolves every HTTP status as `{ data, status }`
 * instead of throwing, so 4xx and 5xx answers never reach `retry`; only network and parse errors do.
 */
export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount) => failureCount < MAX_RETRIES,
      },
    },
  })
}
