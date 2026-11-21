import { randomUUID } from "node:crypto";
import { createEventSchema } from "../../../frontend/src/api/generated/event-schemas/event-schemas";
import type { EventSchemaRead, SourceCreate, SourceRead, TeamRead } from "../../../frontend/src/api/generated/model";
import {
  createSource,
  deleteSource,
  getCreateSourceUrl,
  getDeleteSourceUrl,
  getGetSourceUrl,
  getListSourcesUrl,
  getRotateSourceTokenUrl,
  getUpdateSourceUrl,
  rotateSourceToken,
  updateSource,
} from "../../../frontend/src/api/generated/sources/sources";
import {
  MISSING_ID,
  expect,
  ignoreNotImplemented,
  requireImplemented,
  skipIfNotImplemented,
  test,
  type ApiClient,
} from "../../fixtures";
import { SourcesPage } from "../../pages/sources";

/** A one-field event schema in `team`; event schemas have no delete route, so it stays behind. */
async function schemaIn(api: ApiClient, team: TeamRead): Promise<EventSchemaRead> {
  return api
    .callExpecting(createEventSchema, 201, {
      name: `e2e-${randomUUID().slice(0, 8)}`,
      version: 1,
      team_id: team.id,
      json_schema: { type: "object", properties: { workflowId: { type: "string" } } },
    })
    .catch(skipIfNotImplemented);
}

/** A webhook source in `team` with `schema` as its fixed schema. */
async function sourceIn(api: ApiClient, team: TeamRead, schema: EventSchemaRead): Promise<SourceRead> {
  const suffix = randomUUID().slice(0, 8);
  const body: SourceCreate = {
    slug: `e2e-${suffix}`,
    name: `E2E source ${suffix}`,
    type: "webhook",
    team_id: team.id,
    schema_resolution: { mode: "fixed", schema_id: schema.id },
  };
  return api.callExpecting(createSource, 201, body).catch(skipIfNotImplemented);
}

/** A `POST /sources` body that validates but names no existing team or schema, so a real route answers 404. */
const probeSource: SourceCreate = {
  slug: "e2e-probe",
  name: "E2E probe",
  type: "webhook",
  team_id: MISSING_ID,
  schema_resolution: { mode: "fixed", schema_id: MISSING_ID },
};

test.describe("GET and POST /api/sources", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListSourcesUrl());
    await requireImplemented(adminApi, "post", getCreateSourceUrl(), probeSource);
    await requireImplemented(adminApi, "post", getRotateSourceTokenUrl(MISSING_ID), {});
  });

  test("a member adds a source and sees its first token once", async ({ asMember: { page, team, api }, adminApi }) => {
    const schema = await schemaIn(api, team);
    const sources = new SourcesPage(page);
    await sources.goto(team.slug);
    const name = `E2E Webhook ${randomUUID().slice(0, 8)}`;

    const response = await sources.addFixedSource(name, `${schema.name} v1`);

    expect(response.status()).toBe(201);
    const created: SourceRead = await response.json();
    try {
      const step = page.getByRole("dialog", { name: `${name} added` });
      await step.getByRole("button", { name: "Create token" }).click();
      await expect(step.getByText("This token is shown only once.")).toBeVisible();
      await expect(sources.tokenField(step)).not.toHaveValue("");
      await expect(step.getByLabel("Send a test event")).toContainText(created.ingest_url);
      await step.getByRole("button", { name: "Done" }).click();
      await expect(sources.row(name)).toContainText(created.slug);
      await expect(page.getByText("This token is shown only once.")).toHaveCount(0);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteSource, 204, created.id));
    }
  });

  test("a viewer sees the sources read-only and the API answers 403", async ({ asViewer: { page, team, api }, adminApi }) => {
    const source = await sourceIn(adminApi, team, await schemaIn(adminApi, team));
    try {
      const sources = new SourcesPage(page);
      await sources.goto(team.slug);

      await expect(sources.row(source.name)).toContainText(source.ingest_url);
      await expect(sources.readOnlyNotice).toBeVisible();
      await expect(sources.newSourceButton).toHaveCount(0);
      await expect(sources.enabledSwitch(source.name)).toHaveCount(0);

      const response = await api.call(createSource, { ...probeSource, team_id: team.id, slug: `e2e-${randomUUID().slice(0, 8)}` });
      expect(response.status).toBe(403);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteSource, 204, source.id));
    }
  });
});

test.describe("GET and PATCH /api/sources/{source_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getGetSourceUrl(MISSING_ID));
    await requireImplemented(adminApi, "patch", getUpdateSourceUrl(MISSING_ID), { name: "Renamed" });
  });

  test("a lead renames a source and turns it off", async ({ asLead: { page, team, api }, adminApi }) => {
    const source = await sourceIn(api, team, await schemaIn(api, team));
    try {
      const sources = new SourcesPage(page);
      await sources.goto(team.slug);
      const name = `${source.name} renamed`;

      await sources.rowAction(source.name, "Edit source");
      await sources.editDialog.getByLabel("Name").fill(name);
      await sources.editDialog.getByRole("button", { name: "Save changes" }).click();
      await expect(page.getByText(`${name} saved`)).toBeVisible();

      await sources.enabledSwitch(name).click();
      await page.reload();
      await expect(sources.enabledSwitch(name)).not.toBeChecked();
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteSource, 204, source.id));
    }
  });

  test("a viewer cannot change a source", async ({ asViewer: { team, api }, adminApi }) => {
    const source = await sourceIn(adminApi, team, await schemaIn(adminApi, team));
    try {
      const response = await api.call(updateSource, source.id, { enabled: false });
      expect(response.status).toBe(403);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteSource, 204, source.id));
    }
  });
});

test.describe("POST /api/sources/{source_id}/token", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "post", getRotateSourceTokenUrl(MISSING_ID), {});
  });

  test("a member rotates the token after confirming and sees the new one once", async ({ asMember: { page, team, api }, adminApi }) => {
    const source = await sourceIn(api, team, await schemaIn(api, team));
    try {
      const sources = new SourcesPage(page);
      await sources.goto(team.slug);

      await sources.rowAction(source.name, "Rotate token");
      await sources.rotateDialog(source.name).getByRole("button", { name: "Rotate token" }).click();

      const reveal = page.getByRole("dialog", { name: `New token for ${source.name}` });
      await expect(reveal.getByText("This token is shown only once.")).toBeVisible();
      await expect(sources.tokenField(reveal)).not.toHaveValue("");
      await reveal.getByRole("button", { name: "Done" }).click();
      await expect(reveal).toBeHidden();
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteSource, 204, source.id));
    }
  });

  test("a viewer gets 403", async ({ asViewer: { team, api }, adminApi }) => {
    const source = await sourceIn(adminApi, team, await schemaIn(adminApi, team));
    try {
      const response = await api.call(rotateSourceToken, source.id);
      expect(response.status).toBe(403);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteSource, 204, source.id));
    }
  });
});

test.describe("DELETE /api/sources/{source_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "delete", getDeleteSourceUrl(MISSING_ID));
  });

  test("a member deletes a source after confirming", async ({ asMember: { page, team, api } }) => {
    const source = await sourceIn(api, team, await schemaIn(api, team));
    const sources = new SourcesPage(page);
    await sources.goto(team.slug);

    await sources.rowAction(source.name, "Delete source");
    await sources.deleteDialog(source.name).getByRole("button", { name: "Delete source" }).click();

    await expect(page.getByText(`${source.name} deleted`)).toBeVisible();
    await expect(sources.row(source.name)).toHaveCount(0);
  });

  test("a viewer gets 403", async ({ asViewer: { team, api }, adminApi }) => {
    const source = await sourceIn(adminApi, team, await schemaIn(adminApi, team));
    try {
      const response = await api.call(deleteSource, source.id);
      expect(response.status).toBe(403);
    } finally {
      await ignoreNotImplemented(() => adminApi.callExpecting(deleteSource, 204, source.id));
    }
  });
});
