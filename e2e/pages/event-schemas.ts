import type { Locator, Page } from "@playwright/test";

/** The team's event schemas: the list at `/teams/$team/schemas`, the editor at `…/new` and a version's page. */
export class EventSchemasPage {
  readonly table: Locator;
  readonly newSchemaLink: Locator;
  readonly newVersionLink: Locator;
  readonly readOnlyNotice: Locator;
  readonly name: Locator;
  readonly jsonSchema: Locator;
  readonly fields: Locator;
  readonly sample: Locator;
  readonly checkSampleButton: Locator;
  readonly problems: Locator;

  constructor(readonly page: Page) {
    this.table = page.getByRole("table", { name: "Event schemas" });
    this.newSchemaLink = page.getByRole("link", { name: "New schema" });
    this.newVersionLink = page.getByRole("link", { name: "New version" });
    this.readOnlyNotice = page.getByText("Only members and leads can change this.");
    this.name = page.getByLabel("Name");
    this.jsonSchema = page.getByRole("textbox", { name: "JSON Schema" });
    this.fields = page.getByRole("list", { name: "Fields", exact: true });
    this.sample = page.getByLabel("Sample event");
    this.checkSampleButton = page.getByRole("button", { name: "Check sample" });
    this.problems = page.getByRole("list", { name: "Problems" });
  }

  async goto(teamSlug: string): Promise<void> {
    await this.page.goto(`/teams/${teamSlug}/schemas`);
  }

  /** The page of one schema version. */
  async gotoSchema(teamSlug: string, schemaId: string): Promise<void> {
    await this.page.goto(`/teams/${teamSlug}/schemas/${schemaId}`);
  }

  /** The link on a schema name in the list, which opens its latest version. */
  schemaLink(name: string): Locator {
    return this.table.getByRole("link", { name, exact: true });
  }

  /** Writes a new schema with `name` and `jsonSchema` in the editor and saves it. */
  async create(name: string, jsonSchema: object): Promise<void> {
    await this.newSchemaLink.click();
    await this.name.fill(name);
    await this.jsonSchema.fill(JSON.stringify(jsonSchema, null, 2));
    await this.page.getByRole("button", { name: "Save schema" }).click();
  }

  /** Checks `payload` against the open schema with Check sample. */
  async checkSample(payload: object): Promise<void> {
    await this.sample.fill(JSON.stringify(payload));
    await this.checkSampleButton.click();
  }
}
