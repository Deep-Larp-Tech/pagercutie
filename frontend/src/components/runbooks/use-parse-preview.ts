import { useMemo } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { Condition, RunbookFormat, RunbookParseResult, Step } from '@/api/generated/model'
import { getParseRunbookUrl, parseRunbook } from '@/api/generated/runbooks/runbooks'
import { useDebouncedValue } from '@/hooks/use-debounced-value'
import { unexpectedStatusMessage } from '@/lib/api'
import { OFFLINE } from '@/lib/pagination'
import { bodyIssues } from '@/lib/validation-errors'

/** How long the text must stay unchanged before it is parsed (ms). */
export const PARSE_DEBOUNCE_MS = 400

/** What the preview shows. */
export type ParsePreviewState =
  /** No text yet. */
  | { kind: 'empty' }
  /** The first parse is on its way. */
  | { kind: 'loading' }
  /** Steps, warnings and condition; `updating` while a newer text waits for its answer. */
  | { kind: 'parsed'; result: RunbookParseResult; updating: boolean }
  /** `422`: the text does not fit its format, e.g. YAML that is not the step model. */
  | { kind: 'invalid'; messages: string[]; updating: boolean }
  /** Any other failure, with the message to show. */
  | { kind: 'failed'; message: string; updating: boolean }

/** A saved runbook's format, text and parse result, shown without a request while the text is unchanged. */
export interface SavedParse {
  format: RunbookFormat
  original: string
  attach: Condition | null
  steps: Step[]
}

/**
 * Parses `original` as `format` with `POST /runbooks/parse` once it has stopped changing for `PARSE_DEBOUNCE_MS`.
 * The last answer stays on screen while the next one loads; an aborted or superseded request is cancelled.
 */
export function useParsePreview(format: RunbookFormat, original: string, saved?: SavedParse): ParsePreviewState {
  const request = useMemo(() => ({ format, original }), [format, original])
  const debounced = useDebouncedValue(request, PARSE_DEBOUNCE_MS)
  const isSaved = (value: { format: RunbookFormat; original: string }) =>
    saved !== undefined && value.format === saved.format && value.original === saved.original
  const query = useQuery({
    queryKey: [getParseRunbookUrl(), debounced],
    queryFn: ({ signal }) => parseRunbook(debounced, { signal }),
    enabled: debounced.original.trim() !== '' && !isSaved(debounced),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })

  if (original.trim() === '') return { kind: 'empty' }
  if (saved !== undefined && isSaved(request)) {
    return { kind: 'parsed', result: { attach: saved.attach, steps: saved.steps, warnings: [] }, updating: false }
  }
  const updating = request !== debounced || query.isFetching
  if (query.isError) return { kind: 'failed', message: OFFLINE, updating }
  const response = query.data
  if (response === undefined) return { kind: 'loading' }
  switch (response.status) {
    case 200:
      return { kind: 'parsed', result: response.data, updating }
    case 400:
      return { kind: 'failed', message: "Couldn't read the text. Reload the page and try again.", updating }
    case 422: {
      const messages = bodyIssues(response.data).map((issue) => issue.message)
      return {
        kind: 'invalid',
        messages: messages.length > 0 ? messages : ['The text does not fit the chosen format.'],
        updating,
      }
    }
    case 401:
      return { kind: 'loading' }
    default:
      return { kind: 'failed', message: unexpectedStatusMessage(response), updating }
  }
}
