import { expect, test, type Page } from "@playwright/test";
import { toFunctionSelector } from "viem";

// Read-only fault injection on the isolated Anvil RPC. Never touch real networks.
async function failGetter(page: Page, signature: string) {
  const selector = toFunctionSelector(signature).slice(2).toLowerCase();
  await page.route("http://localhost:8548/", async (route) => {
    const body = route.request().postDataJSON();
    const calls = Array.isArray(body) ? body : [body];
    const failing = new Set(calls.filter((call) => call.method === "eth_call"
      && String(call.params?.[0]?.data).toLowerCase().includes(selector)).map((call) => call.id));
    if (!failing.size) return route.continue();
    const response = await route.fetch();
    const data = await response.json();
    const results = (Array.isArray(data) ? data : [data]).map((result) => failing.has(result.id)
      ? { jsonrpc: "2.0", id: result.id, error: { code: -32000, message: "Test RPC fee read unavailable" } }
      : result);
    await route.fulfill({ response, json: Array.isArray(data) ? results : results[0] });
  });
}

async function openFinalCreateStep(page: Page) {
  await page.goto("/#/create");
  await page.getByTestId("create-question").fill("Will the fee error test recover?");
  await page.getByTestId("create-next").click();
  await page.getByTestId("create-next").click();
  await page.getByTestId("mode-advanced").click();
  await page.getByTestId("create-regex").fill("fee error test");
  await page.getByTestId("create-next").click();
}

test("failed platform getter pauses trading and recovers with the correct rate", async ({ page }) => {
  await failGetter(page, "protocolFee()");
  await page.goto("/#/market/0");
  await expect(page.getByTestId("trade-fees-unavailable")).toContainText("Trading is paused");
  await page.getByTestId("amount-input").fill("100");
  await expect(page.getByTestId("quote-shares")).not.toHaveText("—");
  await expect(page.getByTestId("trade-submit")).toBeDisabled();
  await expect(page.getByTestId("trade-fees")).toHaveCount(0);
  await page.unrouteAll({ behavior: "wait" });
  await expect(page.getByTestId("trade-fees")).toContainText("Platform fee2.2%", { timeout: 25_000 });
  await expect(page.getByTestId("trade-submit")).toBeEnabled();
});

test("failed factory fee read blocks creation until an explicit retry succeeds", async ({ page }) => {
  await failGetter(page, "protocolFee()");
  await openFinalCreateStep(page);
  await expect(page.getByTestId("create-fees")).toContainText("Platform fees unavailable", { timeout: 20_000 });
  await expect(page.getByTestId("create-submit")).toBeDisabled();
  await page.unrouteAll({ behavior: "wait" });
  await page.getByTestId("create-fees").getByRole("button", { name: "Retry" }).click();
  await expect(page.getByTestId("create-fees")).toContainText("Total trading fee: 4.2%");
  await expect(page.getByTestId("create-submit")).toBeEnabled();
});

test("treasury balance errors are visible and retryable, not shown as zero", async ({ page }) => {
  await failGetter(page, "protocolFeesAccrued()");
  await page.goto("/#/market/0");
  await expect(page.getByTestId("protocol-fees-read-error")).toBeVisible();
  await expect(page.getByTestId("protocol-fees-accrued")).toHaveText("Unavailable");
  await expect(page.getByTestId("collect-protocol-fees")).toBeDisabled();
  await page.unrouteAll({ behavior: "wait" });
  await page.getByTestId("protocol-fees-read-error").getByRole("button", { name: "Retry" }).click();
  await expect(page.getByTestId("protocol-fees-accrued")).toHaveText("0.00");
  await expect(page.getByTestId("protocol-fees-read-error")).toHaveCount(0);
});
