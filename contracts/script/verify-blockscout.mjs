#!/usr/bin/env node
// Verify a deployment on its Blockscout instance via the v2 standard-input API.
//   node script/verify-blockscout.mjs [gnosis|sepolia]   (run from contracts/, after forge build)
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const NETWORKS = {
  gnosis: { blockscout: "https://gnosisscan.io", rpc: "https://rpc.gnosischain.com", testUsdc: false },
  sepolia: {
    blockscout: "https://eth-sepolia.blockscout.com",
    rpc: "https://ethereum-sepolia-rpc.publicnode.com",
    testUsdc: true, // usdc slot is our own TestUSDC — verify it too
  },
};

const network = process.argv[2] ?? "gnosis";
const net = NETWORKS[network];
if (!net) {
  console.error(`unknown network "${network}" — expected one of: ${Object.keys(NETWORKS).join(", ")}`);
  process.exit(1);
}
const d = JSON.parse(readFileSync(`deployments/${network}.json`, "utf8"));

const cast = (...a) => execFileSync("cast", a).toString().trim();
const mktImpl = cast("call", "--rpc-url", net.rpc, d.factory, "marketImplementation()(address)");
const fpmmImpl = cast("call", "--rpc-url", net.rpc, d.factory, "fpmmImplementation()(address)");

const targets = [
  { addr: d.conditionalTokens, path: "src/tokens/ConditionalTokens.sol", name: "ConditionalTokens", args: "" },
  { addr: d.dkimRegistry, path: "src/dkim/DKIMRegistry.sol", name: "DKIMRegistry", args: "" },
  {
    addr: d.verifier,
    path: "src/dkim/DKIMVerifier.sol",
    name: "DKIMVerifier",
    args: cast("abi-encode", "c(address)", d.dkimRegistry),
  },
  { addr: mktImpl, path: "src/market/HeadlineMarket.sol", name: "HeadlineMarket", args: "" },
  { addr: fpmmImpl, path: "src/market/FPMM.sol", name: "FPMM", args: "" },
  {
    addr: d.factory,
    path: "src/market/MarketFactory.sol",
    name: "MarketFactory",
    args: cast("abi-encode", "c(address,address,address,address,address,uint256,address)", d.conditionalTokens, d.verifier, mktImpl, fpmmImpl,
      cast("call", "--rpc-url", net.rpc, d.factory, "judge()(address)"),
      cast("call", "--rpc-url", net.rpc, d.factory, "protocolFee()(uint256)").split(" ")[0],
      cast("call", "--rpc-url", net.rpc, d.factory, "feeRecipient()(address)")),
  },
];
if (net.testUsdc) {
  targets.push({ addr: d.usdc, path: "src/tokens/TestUSDC.sol", name: "TestUSDC", args: "" });
}

if (d.regexLib) targets.push({addr:d.regexLib,path:"src/lib/RegexLib.sol",name:"RegexLib",args:""});
if (d.emailBodyStore) targets.push({addr:d.emailBodyStore,path:"src/dkim/EmailBodyStore.sol",name:"EmailBodyStore",args:""});

for (const t of targets) {
  let stdJson = execFileSync("forge", ["verify-contract", "--show-standard-json-input", t.addr, `${t.path}:${t.name}`]).toString();
  if (t.name === "HeadlineMarket" && d.regexLib) {
    const input = JSON.parse(stdJson);
    input.settings.libraries = {"src/lib/RegexLib.sol": {RegexLib:d.regexLib}};
    stdJson = JSON.stringify(input);
  }
  const fd = new FormData();
  fd.append("compiler_version", "v0.8.28+commit.7893614a");
  fd.append("license_type", "mit");
  fd.append("contract_name", t.name);
  const args = t.args.replace(/^0x/, "");
  if (args) {
    fd.append("constructor_args", args);
    fd.append("autodetect_constructor_args", "false");
  } else {
    fd.append("autodetect_constructor_args", "true");
  }
  fd.append("files[0]", new Blob([stdJson], { type: "application/json" }), "standard_input.json");
  const r = await fetch(`${net.blockscout}/api/v2/smart-contracts/${t.addr}/verification/via/standard-input`, {
    method: "POST",
    body: fd,
  });
  console.log(`${t.name} @ ${t.addr}: ${r.status} ${(await r.text()).slice(0, 120)}`);
}

// poll for final status
await new Promise((r) => setTimeout(r, 20000));
for (const t of targets) {
  const r = await fetch(`${net.blockscout}/api/v2/smart-contracts/${t.addr}`);
  const j = await r.json().catch(() => ({}));
  console.log(`${t.name}: verified=${j.is_verified ?? j.is_fully_verified ?? false}`);
}
