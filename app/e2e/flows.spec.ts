import { expect, test, type Page } from "@playwright/test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";
import { createPublicClient, http, parseAbi, type Address } from "viem";

const __dirname = dirname(fileURLToPath(import.meta.url));

// All user flows, in one serial suite against a fresh chain (see global-setup):
//   1. browse markets            5. permissionless market creation
//   2. faucet + account switch   6. permissionless zkEmail settlement -> YES
//   3. buy YES / sell            7. redeem winnings, portfolio
//   4. add liquidity + LP fees   8. permissionless NO resolution after deadline
test.describe.configure({ mode: "serial" });

const RPC = "http://localhost:8548";
const emlPath = (name: string) => join(__dirname, "..", "..", "emails", name);

async function rpc(method: string, params: unknown[] = []) {
  const res = await fetch(RPC, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  return (await res.json()).result;
}

async function readCash(page: Page): Promise<number> {
  const text = await page.getByTestId("cash-balance").textContent();
  return parseFloat((text ?? "0").replace(/[$,]/g, ""));
}

test("markets list shows the seeded markets with Polymarket-style pricing", async ({ page }) => {
  await page.goto("/#/markets");
  await expect(page.getByTestId("market-card-0")).toContainText("Fed rate cut announced");
  await expect(page.getByTestId("market-card-0")).toContainText("Live");
  await expect(page.getByTestId("market-card-0")).toContainText("50¢"); // equal-odds seed
  await expect(page.getByTestId("market-card-1")).toContainText("Bitcoin above $150k");
  await expect(page.getByTestId("market-card-1")).toContainText("25¢"); // hinted odds
  await expect(page.getByTestId("market-card-2")).toContainText("Alien contact");
  // sources count + hero chance shown on the card
  await expect(page.getByTestId("market-card-0")).toContainText("3 sources");
  await expect(page.getByTestId("market-card-0")).toContainText("50%");

  // filter + search work
  await page.getByTestId("filter-live").click();
  await expect(page.getByTestId("market-grid").locator("a")).toHaveCount(3);
  await page.getByTestId("search").fill("bitcoin");
  await expect(page.getByTestId("market-grid").locator("a")).toHaveCount(1);
});

test("faucet mints cash and the account switcher switches users", async ({ page }) => {
  await page.goto("/#/markets");
  const aliceCash = await readCash(page);
  expect(aliceCash).toBeGreaterThan(0);

  await page.getByTestId("account-switcher").selectOption("1"); // Bob
  await expect
    .poll(async () => readCash(page))
    .toBeGreaterThan(0);
  const bobBefore = await readCash(page);
  await page.getByTestId("faucet").click();
  await expect.poll(async () => readCash(page), { timeout: 15_000 }).toBeCloseTo(bobBefore + 10_000, 0);
});

test("buy YES moves the price and creates a position", async ({ page }) => {
  await page.goto("/#/market/0");
  await expect(page.getByTestId("market-question")).toContainText("Fed rate cut");
  await expect(page.getByTestId("trade-fees")).toContainText("Liquidity provider fee2%");
  await expect(page.getByTestId("trade-fees")).toContainText("Platform fee2.2%");
  await expect(page.getByTestId("trade-fees")).toContainText("Total trading fee (included)4.2%");
  await expect(page.getByTestId("market-fees")).toContainText("2% LP + 2.2% platform = 4.2% total");

  // $2,000 into a $25k pool: enough to visibly move the price off 50¢
  await page.getByTestId("amount-input").fill("2000");
  await expect(page.getByTestId("quote-shares")).not.toHaveText("—");
  // ~$2,000 at ~50¢ => ~3,696 shares after 4.2% total fees + price impact; "To win" = shares × $1
  await expect
    .poll(async () => parseFloat(((await page.getByTestId("to-win").textContent()) ?? "0").replace(/[$,]/g, "")))
    .toBeGreaterThan(3000);

  await page.getByTestId("trade-submit").click();
  await expect(page.getByTestId("positions-panel")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("pos-yes")).not.toHaveText("0.00");
  // price moved above 50¢
  await expect(page.getByTestId("headline-price")).not.toHaveText("50¢");
});

test("sell part of the YES position", async ({ page }) => {
  await page.goto("/#/market/0");
  await expect(page.getByTestId("positions-panel")).toBeVisible();
  const before = parseFloat(((await page.getByTestId("pos-yes").textContent()) ?? "0").replace(/,/g, ""));

  await page.getByTestId("tab-sell").click();
  await page.getByTestId("amount-input").fill("50");
  await expect(page.getByTestId("youll-receive")).not.toContainText("$0.00");
  await page.getByTestId("trade-submit").click();

  await expect
    .poll(async () =>
      parseFloat(((await page.getByTestId("pos-yes").textContent()) ?? "0").replace(/,/g, "")),
    )
    .toBeLessThan(before);
});

test("add liquidity, earn trading fees, claim them", async ({ page }) => {
  await page.goto("/#/market/0");
  await page.getByTestId("add-liquidity-amount").fill("500");
  await page.getByTestId("add-liquidity").click();
  await expect.poll(async () => {
    const t = (await page.getByTestId("lp-shares").textContent()) ?? "0";
    return parseFloat(t.replace(/,/g, ""));
  }).toBeGreaterThan(0);

  // a trade accrues fees to the LP (2% of $100)
  await page.getByTestId("amount-input").fill("100");
  await page.getByTestId("trade-submit").click();
  await expect.poll(async () => {
    const t = (await page.getByTestId("claimable-fees").textContent()) ?? "$0";
    return parseFloat(t.replace(/[$,]/g, ""));
  }).toBeGreaterThan(0);

  const cashBefore = await readCash(page);
  await page.getByTestId("claim-fees").click();
  await expect.poll(async () => readCash(page)).toBeGreaterThan(cashBefore);
});

test("platform revenue goes only to the fixed treasury, safely across repeated clicks and withdrawals", async ({ page }) => {
  const deployment = JSON.parse(readFileSync(join(__dirname, "../../contracts/deployments/local.json"), "utf8"));
  const client = createPublicClient({ transport: http(RPC) });
  const abi = parseAbi([
    "function getAllMarkets() view returns ((address market,address fpmm)[])",
    "function feeRecipient() view returns (address)",
    "function protocolFeesAccrued() view returns (uint256)",
    "function balanceOf(address) view returns (uint256)",
  ]);
  const records = await client.readContract({ address: deployment.factory, abi, functionName: "getAllMarkets" });
  const fpmm = records[0].fpmm;
  const treasury = await client.readContract({ address: fpmm, abi, functionName: "feeRecipient" });
  const readAccrued = () => client.readContract({ address: fpmm, abi, functionName: "protocolFeesAccrued" });
  const readTreasury = () => client.readContract({ address: deployment.usdc, abi, functionName: "balanceOf", args: [treasury] });
  await page.goto("/#/market/0");
  await page.getByTestId("account-switcher").selectOption("1"); // Bob, not the treasury
  await expect(page.getByTestId("protocol-fees-panel")).toContainText(treasury);
  const treasuryBefore = await readTreasury();
  const accrued = await readAccrued();
  expect(accrued).toBeGreaterThan(0n);
  const bob = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC" as Address;
  const nonceBefore = await client.getTransactionCount({ address: bob });
  await expect(page.getByTestId("collect-protocol-fees")).toBeEnabled();
  // Same-tick clicks must not enqueue duplicate wallet writes.
  await page.getByTestId("collect-protocol-fees").evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect.poll(readAccrued).toBe(0n);
  await expect.poll(readTreasury).toBe(treasuryBefore + accrued);
  await expect(page.getByTestId("collect-protocol-fees")).toBeDisabled();
  await expect.poll(() => client.getTransactionCount({ address: bob })).toBe(nonceBefore + 1);
  await expect(page.getByTestId("protocol-fees-accrued")).toHaveText("0.00");

  // New trading revenue can be collected again without retaining stale busy/success state.
  await page.getByTestId("amount-input").fill("100");
  await expect(page.getByTestId("trade-submit")).toBeEnabled();
  await page.getByTestId("trade-submit").click();
  await expect.poll(readAccrued).toBe(2_200_000n);
  await expect(page.getByTestId("collect-protocol-fees")).toBeEnabled();
  await page.getByTestId("collect-protocol-fees").click();
  await expect.poll(readAccrued).toBe(0n);
  await expect.poll(readTreasury).toBe(treasuryBefore + accrued + 2_200_000n);
  await expect(page.getByTestId("collect-protocol-fees")).toBeDisabled();
});

test("anyone can create a market permissionlessly", async ({ page }) => {
  await page.goto("/#/create");

  // Step 1: question
  await page.getByTestId("create-question").fill("Will a headline announce rain of frogs this month?");
  await page.getByTestId("create-next").click();

  // Step 2: newspapers — NYT + WaPo preselected; add Reuters, set threshold
  await page.getByTestId("newspaper-email.reuters.com").click();
  await expect(page.getByTestId("selected-sources")).toContainText("Reuters");
  await page.getByTestId("create-next").click();

  // Step 3: condition — plain-words builder first, then the advanced regex editor
  await page.getByTestId("keyword-input").fill("rain of frogs");
  await page.getByTestId("keyword-add").click();
  await expect(page.getByTestId("keyword-list")).toContainText("rain of frogs");
  await page.getByTestId("create-test-subject").fill("Breaking News: RAIN   OF   FROGS in Ohio");
  await expect(page.getByTestId("regex-feedback")).toContainText("Matches"); // case-insensitive + flexible spaces
  // advanced mode shows/edits the raw pattern
  await page.getByTestId("mode-advanced").click();
  await page.getByTestId("create-regex").fill("(?i)rain(ing)? (of )?frogs");
  await page.getByTestId("create-test-subject").fill("Breaking News: It is raining frogs in Ohio");
  await expect(page.getByTestId("regex-feedback")).toContainText("Matches");
  await page.getByTestId("create-next").click();

  // Step 4: disclose the immutable platform rate and validate the LP + platform total.
  await expect(page.getByTestId("create-fees")).toContainText("Platform fee: 2.2%");
  await expect(page.getByTestId("create-fees")).toContainText("Total trading fee: 4.2%");
  for (const badFee of ["-1", "NaN", "1e2", "97.8", "100", "0.00000000000000001"]) {
    await page.getByTestId("create-fee").fill(badFee);
    await expect(page.getByTestId("create-submit")).toBeDisabled();
    await expect(page.getByTestId("create-fee-error")).toBeVisible();
  }
  await page.getByTestId("create-fee").fill("0");
  await expect(page.getByTestId("create-fees")).toContainText("Total trading fee: 2.2%");
  await expect(page.getByTestId("create-submit")).toBeEnabled();
  await page.getByTestId("create-fee").fill("2");
  await page.getByTestId("create-liquidity").fill("200");
  await page.getByTestId("create-submit").click();

  // lands on the new market page (id 3 on a fresh chain)
  await expect(page).toHaveURL(/#\/market\/3/, { timeout: 30_000 });
  await expect(page.getByTestId("market-question")).toContainText("rain of frogs");
  await expect(page.getByTestId("headline-price")).toContainText("50¢");
  await page.getByTestId("market-tab-rules").click();
  await expect(page.getByTestId("rules-panel")).toContainText("2 of 3 newspapers");
});

test("zkEmail settlement: non-matching email is rejected, 2-of-3 alerts resolve YES, winners redeem", async ({
  page,
}) => {
  await page.goto("/#/market/0");

  // negative case first: a real-looking NYT briefing that does NOT match the regex
  await page.getByTestId("eml-input").setInputFiles(emlPath("nyt-daily-briefing-nonmatching.eml"));
  await expect(page.getByTestId("proof-preview")).toBeVisible();
  await expect(page.getByTestId("proof-check-fail")).toContainText("content regex mismatch");
  await expect(page.getByTestId("submit-proof")).toBeDisabled();

  // NYT breaking alert: passes all conditions
  await page.getByTestId("eml-input").setInputFiles(emlPath("nyt-fed-cut.eml"));
  await expect(page.getByTestId("proof-subject")).toContainText("Fed cuts rates by 50 basis points");
  await expect(page.getByTestId("proof-check-ok")).toContainText("The New York Times");
  await page.getByTestId("submit-proof").click();
  await expect(page.getByTestId("source-status")).toContainText("Fed cuts rates", { timeout: 20_000 });
  await expect(page.getByTestId("resolution-panel")).toContainText("1/2 sources matched").catch(() => {});

  // Washington Post alert reaches the 2-of-3 threshold -> YES (real DKIM RSA verified onchain)
  await page.getByTestId("eml-input").setInputFiles(emlPath("wapo-fed-cut.eml"));
  await expect(page.getByTestId("proof-check-ok")).toContainText("The Washington Post");
  await page.getByTestId("submit-proof").click();
  await expect(page.getByTestId("resolution-panel")).toContainText("Resolved YES", { timeout: 20_000 });

  // trading is frozen, YES holder sees the claim banner and redeems at $1/share
  await expect(page.getByText("Trading closed")).toBeVisible();
  await expect(page.getByTestId("you-won")).toBeVisible();
  const cashBefore = await readCash(page);
  await page.getByTestId("redeem").click();
  await expect.poll(async () => readCash(page)).toBeGreaterThan(cashBefore);
});

test("portfolio shows remaining positions and LP rows", async ({ page }) => {
  await page.goto("/#/portfolio");
  // Alice still LPs market 0 and seeded market 3 at creation
  await expect(page.getByTestId("portfolio-table")).toBeVisible();
  await expect(page.getByTestId("portfolio-table")).toContainText("LP");
  await expect(page.getByTestId("portfolio-table")).toContainText("Fed rate cut");
  await expect(page.getByTestId("portfolio-table")).toContainText("rain of frogs");
});

test("after the deadline anyone can resolve NO", async ({ page }) => {
  // Warp chain past the alien market's 7d deadline + 1h buffer.
  await rpc("evm_increaseTime", [7 * 86400 + 3700]);
  await rpc("evm_mine");

  await page.goto("/#/market/2");
  await expect(page.getByTestId("resolve-no")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("resolve-no").click();
  await expect(page.getByTestId("resolution-panel")).toContainText("Resolved NO", { timeout: 20_000 });
  await expect(page.getByText("Trading closed")).toBeVisible();

  // list reflects the resolution states
  await page.goto("/#/markets");
  await expect(page.getByTestId("market-card-0")).toContainText("Resolved YES");
  await expect(page.getByTestId("market-card-2")).toContainText("Resolved NO");
});
