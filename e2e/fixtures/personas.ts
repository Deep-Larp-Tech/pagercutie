import { randomUUID } from "node:crypto";
import type { Browser, Page } from "@playwright/test";
import type { TeamRead, TeamRole, UserRead } from "../../frontend/src/api/generated/model";
import { createTeam, deleteTeam, setTeamMember } from "../../frontend/src/api/generated/teams/teams";
import { createUser, deleteUser } from "../../frontend/src/api/generated/users/users";
import { ApiClient, ApiError } from "./api";
import { ignoreNotImplemented, skipIfNotImplemented } from "./implemented";

/** Email of the admin the API creates on start (ADR-0037); compose defaults it to `admin@example.com`. */
export const ADMIN_EMAIL = process.env.APP_BOOTSTRAP_ADMIN_EMAIL ?? "admin@example.com";

/** A logged-in user: `page` belongs to a fresh browser context carrying the same session as `api`. */
export interface Persona {
  page: Page;
  api: ApiClient;
  user: UserRead;
}

/** A persona with a team role in `team`. */
export interface TeamPersona extends Persona {
  team: TeamRead;
}

/** Email no other test uses, so parallel tests never share users. */
export function uniqueEmail(label: string): string {
  return `e2e-${label}-${randomUUID()}@example.com`;
}

/**
 * Logs in as `email`, opens a browser context with the session's `pc_session` cookie, and closes the context
 * afterwards.
 */
export async function withPersona(
  browser: Browser,
  baseURL: string,
  email: string,
  use: (persona: Persona) => Promise<void>,
): Promise<void> {
  const { api, me } = await ApiClient.login(baseURL, email);
  const context = await browser.newContext({ baseURL });
  try {
    if (api.session !== undefined) {
      // Same attributes the API sets (ADR-0035).
      await context.addCookies([
        { name: "pc_session", value: api.session, url: baseURL, httpOnly: true, sameSite: "Lax" },
      ]);
    }
    await use({ page: await context.newPage(), api, user: me.user });
  } finally {
    await context.close();
  }
}

/** Creates a global-role `user` with a unique email; skips the test while `createUser` is a stub. */
export async function createUniqueUser(adminApi: ApiClient, label: string): Promise<UserRead> {
  return adminApi
    .callExpecting(createUser, 201, { email: uniqueEmail(label), display_name: `E2E ${label}` })
    .catch(skipIfNotImplemented);
}

/**
 * Deletes a team created by a fixture; ignores `deleteTeam` while it is a stub, and a `409` from a team that still owns
 * data the API cannot delete yet (event schemas have no delete route). The team's unique slug keeps later runs apart.
 */
async function deleteCreatedTeam(adminApi: ApiClient, teamId: string): Promise<void> {
  try {
    await ignoreNotImplemented(() => adminApi.callExpecting(deleteTeam, 204, teamId));
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 409)) throw error;
  }
}

/** Deletes a user created by a fixture; ignores `deleteUser` while it is a stub. */
export async function deleteCreatedUser(adminApi: ApiClient, user: UserRead): Promise<void> {
  await ignoreNotImplemented(() => adminApi.callExpecting(deleteUser, 204, user.id));
}

/**
 * Creates a user, a team and a membership with `role`, yields the logged-in persona, then deletes the team and the
 * user. Skips the test while any setup route is a stub; teardown ignores delete routes that are still stubs, since
 * unique data keeps parallel runs apart.
 */
export async function withTeamPersona(
  browser: Browser,
  baseURL: string,
  adminApi: ApiClient,
  role: TeamRole,
  use: (persona: TeamPersona) => Promise<void>,
): Promise<void> {
  const user = await createUniqueUser(adminApi, role);
  try {
    const suffix = randomUUID();
    const team = await adminApi
      .callExpecting(createTeam, 201, { slug: `e2e-${suffix}`, name: `E2E team ${suffix.slice(0, 8)}` })
      .catch(skipIfNotImplemented);
    try {
      await adminApi.callExpecting(setTeamMember, 200, team.id, user.id, { role }).catch(skipIfNotImplemented);
      await withPersona(browser, baseURL, user.email, (persona) => use({ ...persona, team }));
    } finally {
      await deleteCreatedTeam(adminApi, team.id);
    }
  } finally {
    await deleteCreatedUser(adminApi, user);
  }
}
