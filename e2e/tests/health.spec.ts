import { getHealth } from "../../frontend/src/api/generated/health/health";
import { ApiClient, expect, test } from "../fixtures";

test("GET /api/health answers 200", async ({ apiBaseURL }) => {
  const response = await ApiClient.anonymous(apiBaseURL).call(getHealth);
  expect(response.status).toBe(200);
});
