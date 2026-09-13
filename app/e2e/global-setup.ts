import { execSync, spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const RPC = "http://localhost:8548";
const PID_FILE = join(__dirname, ".anvil-pid");

async function rpcReady(): Promise<boolean> {
  try {
    const res = await fetch(RPC, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_chainId", params: [] }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export default async function globalSetup() {
  // Fresh chain per run => deterministic market ids and balances.
  try {
    execSync("pkill -f 'anvil --port 8548'");
  } catch {
    /* none running */
  }
  const anvil = spawn(
    "anvil",
    ["--port", "8548", "--disable-block-gas-limit", "--disable-code-size-limit", "--silent"],
    { detached: true, stdio: "ignore" },
  );
  anvil.unref();
  writeFileSync(PID_FILE, String(anvil.pid));

  for (let i = 0; i < 50 && !(await rpcReady()); i++) {
    await new Promise((r) => setTimeout(r, 200));
  }
  if (!(await rpcReady())) throw new Error("anvil (e2e, :8548) did not come up");

  // real DKIM keys the deploy registers (dev key for fixtures + real NYT key)
  execSync("node scripts/dkim-keys.mjs", { cwd: join(__dirname, ".."), stdio: "pipe" });
  execSync(
    `forge script script/Deploy.s.sol:Deploy --rpc-url ${RPC} --broadcast ` +
      "--private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    { cwd: join(__dirname, "..", "..", "contracts"), stdio: "pipe" },
  );
  // Playwright starts webServer before globalSetup. Refresh the generated addresses
  // after deployment so the browser never queries the previous chain's factory.
  execSync("node scripts/sync-contracts.mjs", { cwd: join(__dirname, ".."), stdio: "pipe" });
}
