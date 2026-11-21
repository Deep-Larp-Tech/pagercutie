let apiBaseUrl: string | undefined

/**
 * Sets the origin the generated client resolves its `/api/...` URLs against; unset (the default) keeps them
 * relative, as the browser app needs. Node callers without a page origin (the Playwright fixtures) set it once.
 */
export function setApiBaseUrl(url: string | undefined): void {
  apiBaseUrl = url
}

/**
 * Fetch mutator for the orval client (`orval.config.ts`). Resolves to `{ data, status, headers }` for every status,
 * like orval's default fetch client, so the generated per-status response unions stay accurate (ADR-0049).
 *
 * `data` is the parsed JSON body, or `{}` when the body is empty or the status is 204, 205 or 304.
 */
export async function customFetch<T>(url: string, options: RequestInit): Promise<T> {
  const response = await fetch(apiBaseUrl === undefined ? url : new URL(url, apiBaseUrl), options)
  const text = [204, 205, 304].includes(response.status) ? null : await response.text()
  const data: unknown = text ? JSON.parse(text) : {}
  return { data, status: response.status, headers: response.headers } as T
}
