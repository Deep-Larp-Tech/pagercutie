import { useInfiniteQuery, type QueryKey } from '@tanstack/react-query'

/** Largest `limit` a list endpoint accepts (DOMAIN.md §1); lists load this many items per page. */
export const PAGE_LIMIT = 100

/** Shown when a page request gets no answer at all. */
export const OFFLINE = "Couldn't reach PagerCutie. Check your connection and try again."

/** `limit` and `offset` of one page. */
export interface PageParams {
  limit: number
  offset: number
}

/** A generated list response: `200` carries the page's items, any other status an error body. */
interface PageResponse {
  status: number
  data: unknown
}

/** What one page response holds, read by the screen's exhaustive `switch` on its status. */
export type PageResult<T> =
  /** `200`: the page's items. */
  | { kind: 'items'; items: T[] }
  /** A status the user should hear about, with the message to show. */
  | { kind: 'failed'; message: string }
  /** Nothing to show and nothing to say: a `401`, whose sign-in redirect is already under way. */
  | { kind: 'silent' }

/** What a paged list screen renders. */
export type PagedList<T> =
  | { kind: 'loading' }
  /** The first page failed; nothing to list. */
  | { kind: 'failed'; message: string }
  /** Items of every page loaded so far; `moreError` says why the last "Show more" failed. */
  | { kind: 'listed'; items: T[]; moreError: string | null }

/**
 * Folds the pages loaded so far into one `PagedList`. `pages` is `undefined` until the first page answers;
 * `networkError` is set when the last request got no answer.
 */
export function pagedList<T>(pages: readonly PageResult<T>[] | undefined, networkError: boolean): PagedList<T> {
  const [first, ...rest] = pages ?? []
  if (first === undefined) return networkError ? { kind: 'failed', message: OFFLINE } : { kind: 'loading' }
  if (first.kind === 'failed') return first
  if (first.kind === 'silent') return { kind: 'loading' }
  const items = [first, ...rest].flatMap((page) => (page.kind === 'items' ? page.items : []))
  const last = rest.at(-1)
  const moreError = last?.kind === 'failed' ? last.message : networkError ? OFFLINE : null
  return { kind: 'listed', items, moreError }
}

/** A list loaded page by page with `useOffsetPages`. */
export interface OffsetPages<T> {
  list: PagedList<T>
  /** The last page was full, so there may be more. */
  hasMore: boolean
  /** Loads the next page. */
  loadMore: () => void
  /** The next page is loading. */
  loadingMore: boolean
  /** Loads every page again, after a failure. */
  retry: () => void
}

/**
 * Loads a list endpoint `PAGE_LIMIT` items at a time. Lists return no total, so a full page means there may be
 * more. `readPage` turns one response into a `PageResult` with a `switch` over its documented statuses.
 *
 * `queryKey` must differ from any `useQuery` key on the same endpoint (the cached shapes differ) and should start
 * with the generated list key, so invalidating that key refreshes this list too.
 */
export function useOffsetPages<R extends PageResponse, T>(
  queryKey: QueryKey,
  fetchPage: (params: PageParams, signal: AbortSignal) => Promise<R>,
  readPage: (response: R) => PageResult<T>,
): OffsetPages<T> {
  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam, signal }) => fetchPage({ limit: PAGE_LIMIT, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (lastPage, _pages, lastOffset) =>
      lastPage.status === 200 && Array.isArray(lastPage.data) && lastPage.data.length === PAGE_LIMIT
        ? lastOffset + PAGE_LIMIT
        : undefined,
  })
  return {
    list: pagedList(query.data?.pages.map(readPage), query.isError),
    hasMore: query.hasNextPage,
    loadMore: () => void query.fetchNextPage(),
    loadingMore: query.isFetchingNextPage,
    retry: () => void query.refetch(),
  }
}
