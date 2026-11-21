import { test } from "@playwright/test";
import { ApiError, type ApiClient } from "./api";

/** HTTP methods the management API uses. */
export type Method = "get" | "post" | "put" | "patch" | "delete";

/** A well-formed id no row has; item-route probes use it so an implemented route answers `404` and writes nothing. */
export const MISSING_ID = "00000000-0000-0000-0000-000000000000";

/**
 * Route to probe. Mutating methods need a body that passes validation (FastAPI answers `422` before the stub's
 * `501`) and that an implemented route must reject without writing: a duplicate (`409`) or a `MISSING_ID` in the
 * path (`404`).
 */
export type Probe =
  | [method: "get" | "delete", path: string]
  | [method: "post" | "put" | "patch", path: string, body: object];

const implementedByRoute = new Map<string, boolean>();

/**
 * Skips the current test while the route is a `501` stub. The result is cached per worker.
 *
 * `api` must hold a session (`adminApi`): auth runs before validation and the handler, so a logged-out probe answers
 * `401` for stubs and real routes alike. The probe is a raw request because a generated function hides its method,
 * which the side-effect check below needs; build `path` with the generated URL helper (`getCreateUserUrl()`).
 */
export async function requireImplemented(api: ApiClient, ...probe: Probe): Promise<void> {
  const [method, path] = probe;
  const route = `${method.toUpperCase()} ${path}`;
  let implemented = implementedByRoute.get(route);
  if (implemented === undefined) {
    const response = await fetch(new URL(path, api.baseURL), {
      method: method.toUpperCase(),
      headers: { cookie: api.cookieHeader, "content-type": "application/json" },
      body: probe.length === 3 ? JSON.stringify(probe[2]) : undefined,
      redirect: "manual",
    });
    implemented = classify(method, route, response.status, await response.text());
    implementedByRoute.set(route, implemented);
  }
  test.skip(!implemented, `501: ${route} not implemented yet`);
}

function classify(method: Method, route: string, status: number, body: string): boolean {
  if (status === 501) return false;
  if (status === 401) {
    throw new Error(`Probe ${route} answered 401: pass a logged-in client (adminApi).`);
  }
  if (status === 422) {
    throw new Error(`Probe ${route} answered 422 before reaching the handler; fix the probe body or path: ${body}`);
  }
  if (method !== "get" && status >= 200 && status < 300) {
    throw new Error(`Probe ${route} answered ${status} and may have written data; use a body the route rejects.`);
  }
  return true;
}

/** Skips the current test when `error` is an `ApiError` for a `501` stub; rethrows anything else. */
export function skipIfNotImplemented(error: unknown): never {
  if (error instanceof ApiError && error.status === 501) {
    test.skip(true, `501: ${error.operation} not implemented yet`);
  }
  throw error;
}

/** Runs a teardown step and ignores a `501` stub; a route that is not implemented yet has nothing to undo. */
export async function ignoreNotImplemented(step: () => Promise<unknown>): Promise<void> {
  try {
    await step();
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 501)) throw error;
  }
}
