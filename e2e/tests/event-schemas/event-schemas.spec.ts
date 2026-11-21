import { randomUUID } from "node:crypto";
import {
  createEventSchema,
  getEventSchema,
  getGetEventSchemaUrl,
  getListEventSchemasUrl,
  getValidateEventUrl,
} from "../../../frontend/src/api/generated/event-schemas/event-schemas";
import type { EventSchemaCreate } from "../../../frontend/src/api/generated/model";
import { MISSING_ID, expect, requireImplemented, skipIfNotImplemented, test } from "../../fixtures";
import { EventSchemasPage } from "../../pages/event-schemas";

/** A settlement event with a nested error and a three-letter currency (`SCH-3`). */
const settlementSchema = {
  type: "object",
  properties: {
    workflowId: { type: "string" },
    currency: { type: "string", maxLength: 3 },
    error: { type: "object", properties: { code: { type: "string" } }, required: ["code"] },
  },
  required: ["workflowId"],
};

function schemaBody(teamId: string): EventSchemaCreate {
  return { name: `e2e-${randomUUID().slice(0, 8)}`, version: 1, team_id: teamId, json_schema: settlementSchema };
}

test.describe("GET and POST /api/event-schemas, GET /api/event-schemas/{schema_id}", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "get", getListEventSchemasUrl());
    await requireImplemented(adminApi, "get", getGetEventSchemaUrl(MISSING_ID));
  });

  test("a member writes a schema, sees its fields and adds a version", async ({ asMember: { page, team } }) => {
    const schemas = new EventSchemasPage(page);
    const name = `e2e-${randomUUID().slice(0, 8)}`;
    await schemas.goto(team.slug);

    await schemas.create(name, settlementSchema);

    await expect(page.getByRole("heading", { level: 1, name: `${name} v1` })).toBeVisible();
    await expect(schemas.fields).toContainText("currencystringat most 3 characters");
    await schemas.newVersionLink.click();
    await expect(page.getByRole("heading", { level: 1, name: `New version of ${name}` })).toBeVisible();
    await page.getByRole("button", { name: "Save version" }).click();
    await expect(page.getByRole("heading", { level: 1, name: `${name} v2` })).toBeVisible();

    await schemas.goto(team.slug);
    await expect(page.getByRole("list", { name: `Versions of ${name}` })).toContainText("v2v1");
  });

  test("a viewer reads schemas without New schema, and the API answers 403", async ({ asViewer: { page, team, api }, adminApi }) => {
    const schema = await adminApi.callExpecting(createEventSchema, 201, schemaBody(team.id)).catch(skipIfNotImplemented);
    const schemas = new EventSchemasPage(page);
    await schemas.goto(team.slug);

    await expect(schemas.schemaLink(schema.name)).toBeVisible();
    await expect(schemas.readOnlyNotice).toBeVisible();
    await expect(schemas.newSchemaLink).toHaveCount(0);

    const response = await api.call(createEventSchema, schemaBody(team.id));
    expect(response.status).toBe(403);
  });

  test("a user outside the team may still read the schema", async ({ asUser: { api }, adminApi, asLead: { team } }) => {
    const schema = await adminApi.callExpecting(createEventSchema, 201, schemaBody(team.id)).catch(skipIfNotImplemented);

    const response = await api.call(getEventSchema, schema.id);

    expect(response.status).toBe(200);
  });
});

test.describe("POST /api/event-schemas/{schema_id}/validate", () => {
  test.beforeEach(async ({ adminApi }) => {
    await requireImplemented(adminApi, "post", getValidateEventUrl(MISSING_ID), { payload: {} });
  });

  test("Check a sample shows a match, then each problem with its path", async ({ asMember: { page, team, api } }) => {
    const schema = await api.callExpecting(createEventSchema, 201, schemaBody(team.id)).catch(skipIfNotImplemented);
    const schemas = new EventSchemasPage(page);
    await schemas.gotoSchema(team.slug, schema.id);

    await schemas.checkSample({ workflowId: "wf-8f21", currency: "USD" });
    await expect(page.getByText("The sample matches the schema.")).toBeVisible();

    await schemas.checkSample({ currency: "EURO" });
    await expect(page.getByText("The sample doesn't match the schema.")).toBeVisible();
    await expect(schemas.problems).toContainText("/currency");
  });
});
