import type { RunbookParseRequest } from "../../../frontend/src/api/generated/model";
import { parseRunbook } from "../../../frontend/src/api/generated/runbooks/runbooks";
import { expect, skipIfNotImplemented, test } from "../../fixtures";
import { RunbookEditorPage } from "../../pages/runbooks";

const probe: RunbookParseRequest = { format: "text", original: "Probe" };
const link: RunbookParseRequest = { format: "link", original: "https://wiki.example.com/runbook" };
const unknownGuard: RunbookParseRequest = {
  format: "structured",
  original: [
    "runbook: x",
    "steps:",
    "  - action: wait",
    "    seconds: 5",
    "  - if: latency is still high",
    "    action: manual",
    "    text: Call on-call",
  ].join("\n"),
};

test.describe("POST /api/runbooks/parse", () => {
  // Parsing writes nothing, so a real call stands in for `requireImplemented`, which refuses a 2xx on POST.
  test.beforeEach(async ({ adminApi }) => {
    await adminApi
      .callExpecting(parseRunbook, 200, probe)
      .catch(skipIfNotImplemented);
  });

  test("a member previews the Markdown and free-text samples (RUN-8)", async ({ asMember: { page, team } }) => {
    const editor = new RunbookEditorPage(page);
    await editor.gotoNew(team.slug);

    await editor.insertExample("Markdown: payments error rate");
    await expect(editor.parsedSteps).toHaveCount(4);
    await expect(editor.parsedSteps.first()).toContainText("Manual step");

    await editor.insertExample("Free text: pricing latency");
    await expect(editor.parsedSteps).toHaveCount(1);
    await expect(editor.parsedSteps.first()).toContainText("it's usually the cache");
  });

  test("a viewer may parse too: it saves nothing", async ({ asViewer: { api } }) => {
    const response = await api.call(parseRunbook, link);

    expect(response.status).toBe(200);
  });

  test("an unrecognised guard stays a question and is reported as a warning", async ({ asUser: { api } }) => {
    const result = await api.callExpecting(parseRunbook, 200, unknownGuard);

    expect(result.steps[1].if).toBe("latency is still high");
    expect(result.warnings).toEqual(["Step 2: the guard 'latency is still high' is not recognised; a human answers it"]);
  });
});
