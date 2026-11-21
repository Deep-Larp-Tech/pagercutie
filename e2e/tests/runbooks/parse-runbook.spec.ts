import { getListRunbooksUrl, parseRunbook } from "../../../frontend/src/api/generated/runbooks/runbooks";
import { RunbookFormat } from "../../../frontend/src/api/generated/model";
import { expect, requireImplemented, test } from "../../fixtures";

// REQUIREMENTS §6.2 sample 2.
const PAYMENTS_MARKDOWN = `# HighErrorRate on payments-api
1. Open the payments dashboard and check if errors are in one region only.
2. If one region: fail traffic over to the other region (needs approval from the team lead).
3. If all regions: check the last deployment and roll it back.
4. Post an update in the #payments-incidents channel every 15 minutes.
`;

test.describe("POST /api/runbooks/parse", () => {
  test.beforeEach(async ({ adminApi }) => {
    // The preview always answers 200 or 422, so probe a sibling route implemented with it.
    await requireImplemented(adminApi, "get", getListRunbooksUrl());
  });

  test("a Markdown runbook previews as a checklist of manual steps", async ({ asUser: { api } }) => {
    const result = await api.callExpecting(parseRunbook, 200, { format: RunbookFormat.markdown, original: PAYMENTS_MARKDOWN });

    expect(result.steps.map((step) => (step.action === "manual" ? step.text : step.action))).toEqual([
      "Open the payments dashboard and check if errors are in one region only.",
      "If one region: fail traffic over to the other region (needs approval from the team lead).",
      "If all regions: check the last deployment and roll it back.",
      "Post an update in the #payments-incidents channel every 15 minutes.",
    ]);
    expect(result.warnings).toEqual([]);
  });

  test("an unrecognised guard is reported as a warning", async ({ asUser: { api } }) => {
    const original = [
      "runbook: x",
      "steps:",
      "  - action: wait",
      "    seconds: 5",
      "  - if: latency is still high",
      "    action: manual",
      "    text: Call on-call",
    ].join("\n");

    const result = await api.callExpecting(parseRunbook, 200, { format: RunbookFormat.structured, original });

    expect(result.steps[1].if).toBe("latency is still high");
    expect(result.warnings).toEqual(["Step 2: the guard 'latency is still high' is not recognised; a human answers it"]);
  });
});
