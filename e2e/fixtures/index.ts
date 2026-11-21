import { test as base } from "@playwright/test";
import { setApiBaseUrl } from "../../frontend/src/api/fetcher";
import { ApiClient } from "./api";
import {
  ADMIN_EMAIL,
  createUniqueUser,
  deleteCreatedUser,
  withPersona,
  withTeamPersona,
  type Persona,
  type TeamPersona,
} from "./personas";

export { expect } from "@playwright/test";
export type { UserCreate } from "../../frontend/src/api/generated/model";
export { ApiClient, ApiError } from "./api";
export { MISSING_ID, ignoreNotImplemented, requireImplemented, skipIfNotImplemented } from "./implemented";
export { ADMIN_EMAIL, uniqueEmail, type Persona, type TeamPersona } from "./personas";

/** Test-scoped fixtures: one logged-in persona per role, each in its own browser context. */
interface PersonaFixtures {
  /** The bootstrap admin (`APP_BOOTSTRAP_ADMIN_EMAIL`). */
  asAdmin: Persona;
  /** `lead` of a team created for this test. */
  asLead: TeamPersona;
  /** `member` of a team created for this test. */
  asMember: TeamPersona;
  /** `viewer` of a team created for this test. */
  asViewer: TeamPersona;
  /** Global role `user` with no memberships. */
  asUser: Persona;
}

/** Worker-scoped fixtures. */
interface WorkerFixtures {
  /** The project's `baseURL`; the generated client resolves its `/api/...` URLs against it in this worker. */
  apiBaseURL: string;
  /** Client holding the bootstrap admin's session; creates and deletes test data. */
  adminApi: ApiClient;
}

/** Playwright `test` with the PagerCutie fixtures; specs import `test` and `expect` from here only. */
export const test = base.extend<PersonaFixtures, WorkerFixtures>({
  apiBaseURL: [
    async ({}, use, workerInfo) => {
      const baseURL = workerInfo.project.use.baseURL;
      if (baseURL === undefined) throw new Error("playwright.config.ts sets no baseURL");
      setApiBaseUrl(baseURL);
      await use(baseURL);
    },
    { scope: "worker", auto: true },
  ],
  adminApi: [
    async ({ apiBaseURL }, use) => {
      const { api } = await ApiClient.login(apiBaseURL, ADMIN_EMAIL);
      await use(api);
    },
    { scope: "worker" },
  ],
  asAdmin: async ({ browser, apiBaseURL }, use) => {
    await withPersona(browser, apiBaseURL, ADMIN_EMAIL, use);
  },
  asUser: async ({ browser, apiBaseURL, adminApi }, use) => {
    const user = await createUniqueUser(adminApi, "user");
    try {
      await withPersona(browser, apiBaseURL, user.email, use);
    } finally {
      await deleteCreatedUser(adminApi, user);
    }
  },
  asLead: async ({ browser, apiBaseURL, adminApi }, use) => {
    await withTeamPersona(browser, apiBaseURL, adminApi, "lead", use);
  },
  asMember: async ({ browser, apiBaseURL, adminApi }, use) => {
    await withTeamPersona(browser, apiBaseURL, adminApi, "member", use);
  },
  asViewer: async ({ browser, apiBaseURL, adminApi }, use) => {
    await withTeamPersona(browser, apiBaseURL, adminApi, "viewer", use);
  },
});
