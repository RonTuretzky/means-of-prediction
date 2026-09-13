#!/usr/bin/env node
// Settlement bot (backlog D7): turns "permissionless" into "automatic".
//
// Reads newspaper alert emails — from a mailbox over IMAP (Gmail app password) or
// from .eml files — parses each one's real DKIM signature, matches it against every
// live market on the deployment, dry-runs `checkProof` onchain, and submits
// `submitProof` for every accepted (market, source) pair. Also resolves NO on markets
// whose deadline + buffer has passed. If a sender's DKIM key (domain, selector) is
// not yet in the DKIMRegistry, the bot fetches it from DNS and registers it when
// running as the authorized registrar. Other settlement wallets need that key registered first.
//
// Judged markets (criteria != "", no regex) have no local pre-filter: the bot asks the
// market for the prompt key of the signed Subject, and if the LLMJudge has no verdict yet
// it requests one from the Gas Killer fleet (scripts/judge/README.md), signs the returned
// verifyAndUpdate payload, and only then submits the proof.
//
//   node scripts/settlement-bot.mjs --network gnosis --since 2d          # IMAP
//   node scripts/settlement-bot.mjs --network sepolia --eml ../emails/nyt-fed-cut.eml
//
// flags: --dry-run            never send a tx nor talk to the fleet (also implied by no PRIVATE_KEY)
//        --judge-only         only judged markets (skips regex markets and resolveNo)
//        --no-judge           skip judged markets entirely
//        --no-prefix          never warm/resume a per-market prefix (fresh infer + fulfil)
//        --state <path>       prefix-resume state file (default .judge-state.<network>.json)
//        --out <path>         write the JSON report
// env: GMAIL_USER + GMAIL_APP_PASSWORD (IMAP; omit when using --eml)
//      PRIVATE_KEY  (sends registerKey/submitProof/resolveNo/verifyAndUpdate; omit => dry run)
//      RPC_OVERRIDE (optional RPC URL)
//      GK_ROUTER_URL / GK_SHARD_URL / GK_API_KEY / GK_QWEN35_* (judged path; see scripts/judge/README.md)
//      JUDGE_TOKENIZER_TABLE (tokenizer blob; default contracts/test/fixtures/qwen35/tokenizer.bin)
import { receivedEmails } from "./mailbox.mjs";
import { createHash } from "node:crypto";
import { resolveTxt } from "node:dns/promises";
import { readFileSync, writeFileSync, appendFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createPublicClient, createWalletClient, http, parseAbi, keccak256, encodeFunctionData, toFunctionSelector, getAddress, zeroAddress } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { gnosis, sepolia } from "viem/chains";
import { bodyPages } from "../src/lib/body-transport.ts";
import { parseEml, buildEmailProof } from "../src/lib/prover.ts";
import { dnsKeyToHex } from "./dkim.mjs";
import { loadTable, buildIndex, canonicalPromptIds, QWEN35 } from "./judge/tokenizer.mjs";
import * as gk from "./judge/gaskiller.mjs";

// ----------------------------------------------------------------------------- args
const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : def;
};
const flag = (name) => args.includes(`--${name}`);
const emlFiles = args.flatMap((a, i) => (a === "--eml" ? [args[i + 1]] : []));
const networkName = opt("network", "gnosis");
const sinceSpec = opt("since", "2d");
const outPath = opt("out", null);
const statePath = opt("state", `.judge-state.${networkName}.json`);
const dryRun = flag("dry-run") || !process.env.PRIVATE_KEY;
const judgeOnly = flag("judge-only");
const noJudge = flag("no-judge");
const usePrefix = !flag("no-prefix");

const NETS = {
  gnosis: { chain: gnosis, rpc: "https://gnosis-rpc.publicnode.com" },
  sepolia: { chain: sepolia, rpc: "https://ethereum-sepolia-rpc.publicnode.com" },
};
const net = NETS[networkName];
if (!net) throw new Error(`unknown network ${networkName}`);
const deployment = JSON.parse(readFileSync(new URL(`../../contracts/deployments/${networkName}.json`, import.meta.url), "utf8"));
const rpc = process.env.RPC_OVERRIDE ?? net.rpc;
const judgeAddress = deployment.llmJudge ? getAddress(deployment.llmJudge) : null;

// ----------------------------------------------------------------------------- chain
const factoryAbi = parseAbi(["function getAllMarkets() view returns ((address market, address fpmm)[])"]);
const marketAbi = parseAbi([
  "struct Source { string name; string dkimDomain; string fromRegex; string contentRegex; }",
  `struct EmailProof { string domainName; bytes32 publicKeyHash; uint256 timestamp; string fromAddress; string subject; string bodyExcerpt; bytes32 emailNullifier; bytes header; bytes signature; ${deployment.bodyParsingVersion === 1 ? "bytes canonicalBody; uint256 bodyOffset; uint256 bodyLength;" : ""} }`,
  "function question() view returns (string)",
  "function contentRegex() view returns (string)",
  "function contentField() view returns (uint8)",
  "function criteria() view returns (string)",
  "function getSources() view returns (Source[])",
  "function threshold() view returns (uint8)",
  "function matchedCount() view returns (uint256)",
  "function resolution() view returns (uint8)",
  "function windowStart() view returns (uint64)",
  "function deadline() view returns (uint64)",
  "function resolutionBuffer() view returns (uint64)",
  "function sourceMatched(uint256) view returns (bool)",
  "function nullifierUsed(bytes32) view returns (bool)",
  "function checkProof(uint256 sourceIndex, EmailProof proof) view returns (bool ok, string reason)",
  "function promptKeyFor(EmailProof proof) view returns (bytes32 key, bytes subject, bool ok)",
  "function submitProof(uint256 sourceIndex, EmailProof proof)",
  "function resolveNo()",
]);
const bodyStoreAbi = parseAbi([
  "struct EmailProof { string domainName; bytes32 publicKeyHash; uint256 timestamp; string fromAddress; string subject; string bodyExcerpt; bytes32 emailNullifier; bytes header; bytes signature; bytes canonicalBody; uint256 bodyOffset; uint256 bodyLength; }",
  "function chunkForHash(bytes32) view returns (address)",
  "function storeChunk(bytes) returns (address)",
  "function submitWithChunks(address market, uint256 sourceIndex, EmailProof proof, address[] pointers)",
]);
const registryAbi = parseAbi([
  "function isDKIMPublicKeyHashValid(string domainName, bytes32 publicKeyHash) view returns (bool)",
  "function registerKey(string domainName, string selector, bytes exponent, bytes modulus) returns (bytes32)",
  "event DKIMKeyRegistered(string domainName, bytes32 indexed publicKeyHash, string selector)",
]);
// LLMJudge (contracts/src/judge/LLMJudge.sol). The tracked calls are selector-identical to
// GasKillerChat35Sharded so an unmodified fleet serves them — pinned below.
const judgeAbi = parseAbi([
  "function verdictOf(bytes32 key) view returns (uint8)",
  "function prefixKeyOf(bytes32 prefixRoot) view returns (bytes32)",
  "function stateTransitionCount() view returns (uint256)",
  "function fulfil(uint32[] promptIds, uint256 maxNewTokens, uint32[] answerIds, bytes32 pipelineRoot)",
  "function fulfilResumed(uint32[] promptIds, uint256 maxNewTokens, uint32[] answerIds, bytes32 pipelineRoot, bytes32 prefixRoot)",
  "function settlePrefix(uint32[] prefixIds, bytes32 prefixRoot)",
]);
const EXPECTED_SELECTORS = { fulfil: "0x9c98c06e", fulfilResumed: "0x6c4d43bc", settlePrefix: "0x7e8de12c" };
for (const [name, sel] of Object.entries(EXPECTED_SELECTORS)) {
  const got = toFunctionSelector(judgeAbi.find((f) => f.type === "function" && f.name === name));
  if (got !== sel) throw new Error(`LLMJudge ABI drift: ${name} selector ${got} != ${sel}`);
}
const VERDICT = { 0: "None", 1: "Yes", 2: "No" };

const publicClient = createPublicClient({ chain: net.chain, transport: http(rpc, { batch: true }), batch: { multicall: true } });
const account = process.env.PRIVATE_KEY ? privateKeyToAccount(process.env.PRIVATE_KEY) : null;
const walletClient = account ? createWalletClient({ account, chain: net.chain, transport: http(rpc) }) : null;
let nonce = account ? await publicClient.getTransactionCount({ address: account.address, blockTag: "pending" }) : 0;

async function send(desc, req) {
  if (dryRun) return { dry: true };
  const hash = await walletClient.writeContract({ ...req, nonce: nonce++ });
  const receipt = await publicClient.waitForTransactionReceipt({ hash, timeout: 180_000 });
  if (receipt.status !== "success") throw new Error(`${desc}: tx reverted (${hash})`);
  return { hash };
}

/** Sign + broadcast a Gas Killer payload {to, data, value, chain_id, valid_until_block} as-is. */
async function sendPayload(desc, payload) {
  if (dryRun) return { dry: true };
  if (Number(payload.chain_id) !== net.chain.id) throw new Error(`${desc}: payload chain_id ${payload.chain_id} != ${net.chain.id}`);
  const head = await publicClient.getBlockNumber();
  if (head > BigInt(payload.valid_until_block)) {
    throw new gk.GasKillerError(`${desc}: payload expired (head ${head} > valid_until_block ${payload.valid_until_block})`, { code: "PAYLOAD_EXPIRED" });
  }
  const hash = await walletClient.sendTransaction({
    to: getAddress(payload.to),
    data: payload.data,
    value: BigInt(payload.value ?? 0),
    gas: payload.estimated_gas ? (BigInt(payload.estimated_gas) * 13n) / 10n : undefined,
    nonce: nonce++,
  });
  const receipt = await publicClient.waitForTransactionReceipt({ hash, timeout: 180_000 });
  if (receipt.status !== "success") throw new Error(`${desc}: tx reverted (${hash})`);
  return { hash, block: Number(receipt.blockNumber) };
}

// ----------------------------------------------------------------------------- regex mirror
function toJsRegex(pattern) {
  let src = pattern;
  let flags = "";
  if (src.startsWith("(?i)")) {
    src = src.slice(4);
    flags = "i";
  }
  return new RegExp(src, flags);
}
const FIELD = { 0: "subject", 1: "body", 2: "subjectOrBody" };

// ----------------------------------------------------------------------------- markets
async function loadMarkets() {
  const records = await publicClient.readContract({ address: deployment.factory, abi: factoryAbi, functionName: "getAllMarkets" });
  const fields = ["question", "contentRegex", "contentField", "getSources", "threshold", "matchedCount", "resolution", "windowStart", "deadline", "resolutionBuffer"];
  const res = await publicClient.multicall({
    allowFailure: false,
    contracts: records.flatMap((r) => fields.map((functionName) => ({ address: r.market, abi: marketAbi, functionName }))),
  });
  // criteria() only exists on the judged-mode implementation; older clones (Gnosis) revert.
  const crit = await publicClient.multicall({
    allowFailure: true,
    contracts: records.map((r) => ({ address: r.market, abi: marketAbi, functionName: "criteria" })),
  });
  const markets = records.map((r, i) => {
    const v = res.slice(i * fields.length, (i + 1) * fields.length);
    return {
      id: i,
      address: r.market,
      question: v[0],
      contentRegex: v[1],
      contentField: Number(v[2]),
      sources: v[3],
      threshold: Number(v[4]),
      matchedCount: Number(v[5]),
      resolution: Number(v[6]),
      windowStart: Number(v[7]),
      deadline: Number(v[8]),
      resolutionBuffer: Number(v[9]),
      criteria: crit[i].status === "success" ? crit[i].result : "",
    };
  });
  const live = markets.filter((m) => m.resolution === 0);
  const matched = await publicClient.multicall({
    allowFailure: false,
    contracts: live.flatMap((m) => m.sources.map((_, si) => ({ address: m.address, abi: marketAbi, functionName: "sourceMatched", args: [BigInt(si)] }))),
  });
  let k = 0;
  for (const m of live) m.sourceMatched = m.sources.map(() => matched[k++]);
  return markets;
}

// ----------------------------------------------------------------------------- emails
function sinceDate(spec) {
  const m = /^(\d+)([dh])$/.exec(spec);
  if (!m) throw new Error(`bad --since ${spec} (use e.g. 2d or 12h)`);
  const ms = Number(m[1]) * (m[2] === "d" ? 86_400_000 : 3_600_000);
  return new Date(Date.now() - ms);
}

async function collectEmails(domains) {
  const out = [];
  if (emlFiles.length) {
    for (const f of emlFiles) out.push({ id: f, raw: readFileSync(f, "latin1") });
    return out;
  }
  // The DKIM signing domain is often different from the From address. Fetch all
  // received mail in the scan window and filter only after reading the signature.
  for await (const email of receivedEmails({ since: sinceDate(sinceSpec) })) out.push(email);
  return out;
}

// ----------------------------------------------------------------------------- DKIM keys
const keyCache = new Map(); // `${domain}|${selector}` -> publicKeyHash | null
let registeredKeys = null; // from DKIMKeyRegistered events: `${domain}|${selector}` -> hash

async function registryLookup(domain, selector) {
  if (!registeredKeys) {
    registeredKeys = new Map();
    const head = await publicClient.getBlockNumber();
    for (let fromBlock = BigInt(deployment.deployBlock ?? 0); fromBlock <= head; fromBlock += 9000n) {
      const toBlock = fromBlock + 8999n < head ? fromBlock + 8999n : head;
      const logs = await publicClient.getLogs({ address: deployment.dkimRegistry,
        event: registryAbi.find((x) => x.type === "event" && x.name === "DKIMKeyRegistered"), fromBlock, toBlock });
      for (const l of logs) registeredKeys.set(`${l.args.domainName}|${l.args.selector}`, l.args.publicKeyHash);
    }
  }
  const hash = registeredKeys.get(`${domain}|${selector}`);
  if (!hash) return null;
  const valid = await publicClient.readContract({ address: deployment.dkimRegistry, abi: registryAbi, functionName: "isDKIMPublicKeyHashValid", args: [domain, hash] });
  return valid ? hash : null;
}

async function ensureKey(domain, selector, log) {
  const ck = `${domain}|${selector}`;
  if (keyCache.has(ck)) return keyCache.get(ck);
  // 1. already registered (covers rotated-out selectors that DNS no longer serves)
  const known = await registryLookup(domain, selector);
  if (known) {
    keyCache.set(ck, known);
    return known;
  }
  // 2. fetch from DNS and register (authorized registrar only on new deployments)
  let txt;
  try {
    txt = (await resolveTxt(`${selector}._domainkey.${domain}`)).map((r) => r.join("")).join("");
  } catch (e) {
    log(`  DNS lookup failed for ${selector}._domainkey.${domain}: ${e.code ?? e.message}`);
    keyCache.set(ck, null);
    return null;
  }
  const p = /p=([A-Za-z0-9+/=]+)/.exec(txt)?.[1];
  if (!p) {
    log(`  no p= in DNS record for ${selector}._domainkey.${domain}`);
    keyCache.set(ck, null);
    return null;
  }
  const { modulus, exponent } = dnsKeyToHex(p);
  const hash = keccak256(modulus);
  const valid = await publicClient.readContract({ address: deployment.dkimRegistry, abi: registryAbi, functionName: "isDKIMPublicKeyHashValid", args: [domain, hash] });
  if (!valid) {
    if (dryRun) {
      log("  DKIM key not registered; register with the authorized registrar before settlement");
      keyCache.set(ck, null);
      return null;
    }
    log(`  DKIM key ${selector}._domainkey.${domain} not registered — registering${dryRun ? " (dry run)" : ""}`);
    const { request } = await publicClient.simulateContract({ account: account ?? undefined, address: deployment.dkimRegistry, abi: registryAbi, functionName: "registerKey", args: [domain, selector, exponent, modulus] });
    await send("registerKey", request);
  }
  keyCache.set(ck, hash);
  return hash;
}

// ----------------------------------------------------------------------------- judge (Gas Killer)
let tokenIndex = null;
function tokenizerIndex() {
  if (!tokenIndex) {
    const p = process.env.JUDGE_TOKENIZER_TABLE ?? fileURLToPath(new URL("../../contracts/test/fixtures/qwen35/tokenizer.bin", import.meta.url));
    tokenIndex = buildIndex(loadTable(p), QWEN35.specialBase);
  }
  return tokenIndex;
}

// prefix-resume state: marketAddress -> { prefixRoot, prefixIds, settledTx }
const state = existsSync(statePath) ? JSON.parse(readFileSync(statePath, "utf8")) : {};
const saveState = () => writeFileSync(statePath, JSON.stringify(state, null, 2));

const readVerdict = async (key) => VERDICT[Number(await publicClient.readContract({ address: judgeAddress, abi: judgeAbi, functionName: "verdictOf", args: [key] }))];
const prefixSettled = async (root) => (await publicClient.readContract({ address: judgeAddress, abi: judgeAbi, functionName: "prefixKeyOf", args: [root] })) !== `0x${"0".repeat(64)}`;

/**
 * Run one tracked call through the router: POST /tasks, poll to `ready`, sign + send the
 * payload. A 409/expired payload resubmits the same calldata (the inference is not rerun).
 */
async function settleThroughRouter(desc, calldata, log, entry) {
  const retries = Number(process.env.GK_TASK_RETRIES ?? 2);
  for (let attempt = 0; ; attempt++) {
    const head = Number(await publicClient.getBlockNumber());
    const taskId = await gk.submitTask({
      target_address: judgeAddress,
      from_address: account.address,
      call_data: calldata,
      value: 0n,
      block_height: head - Number(process.env.GK_BLOCK_LAG ?? 0),
      transition_index: process.env.GK_TRANSITION_INDEX,
    });
    entry.tasks.push({ desc, taskId });
    log(`     task ${taskId} (${desc}) submitted at block ${head}`);
    try {
      const view = await gk.pollTask(taskId, { onStatus: (v) => log(`     task ${taskId}: ${v.status}`) });
      log(`     payload ready: to ${view.payload.to}, valid until block ${view.payload.valid_until_block}, est. gas ${view.payload.estimated_gas}`);
      const r = await sendPayload(desc, view.payload);
      entry.txs.push({ desc, tx: r.hash });
      log(`     verifyAndUpdate mined: ${r.hash}`);
      return r;
    } catch (e) {
      const expired = gk.isPayloadExpired(e) || e?.code === "EXPIRED" || e?.code === "FAILED";
      if (!expired || attempt >= retries) throw e;
      log(`     ${desc}: ${e.message.slice(0, 160)} — resubmitting (${attempt + 1}/${retries})`);
    }
  }
}

/** Warm the per-market prefix (prefill-only), settle it on the judge, record it in the state file. */
async function warmPrefix(m, prefixIds, log, entry) {
  log(`     warming prefix (${prefixIds.length} ids) via POST /shard/prefix …`);
  const warm = await gk.shardPrefixWarm(gk.buildQwen35Request({ consumer: judgeAddress, promptIds: prefixIds, maxNew: 1 }));
  if (Number(warm.prefix_len) !== prefixIds.length) throw new Error(`prefix warm returned prefix_len ${warm.prefix_len} != ${prefixIds.length}`);
  log(`     prefix_root ${warm.prefix_root} (${warm.segments} segments)`);
  if (await prefixSettled(warm.prefix_root)) {
    log(`     prefix already settled on the judge — skipping settlePrefix`);
  } else {
    if (!warm.settle_calldata?.startsWith(EXPECTED_SELECTORS.settlePrefix)) throw new Error(`settle_calldata is not settlePrefix: ${String(warm.settle_calldata).slice(0, 10)}`);
    await settleThroughRouter("settlePrefix", warm.settle_calldata, log, entry);
    if (!(await prefixSettled(warm.prefix_root))) throw new Error("settlePrefix mined but prefixKeyOf is still zero (judge rejected the prefix — see JudgeRejected logs)");
  }
  state[m.address] = { prefixRoot: warm.prefix_root, prefixIds, settledTx: entry.txs.at(-1)?.tx ?? null, at: new Date().toISOString() };
  saveState();
  return warm.prefix_root;
}

/**
 * Ask the fleet for a verdict on (market, subject) and settle it on the LLMJudge.
 * @returns {Promise<string>} the verdict after settlement (Yes/No/None)
 */
async function requestVerdict(m, key, subjectBytes, log, entry) {
  const { ids, prefixLen, prefixIds } = canonicalPromptIds(tokenizerIndex(), QWEN35.scaffold, m.question, m.criteria, subjectBytes);
  entry.promptIds = ids.length;
  entry.prefixLen = prefixLen;
  log(`     prompt: ${ids.length} ids (prefix ${prefixLen}) — seq_cap ${gk.qwen35Config().seq_cap}, stages ${gk.qwen35Config().stages}`);
  if (dryRun) {
    entry.action = "would-request";
    log(`     (dry run) would ${usePrefix ? "warm/resume the market prefix and " : ""}run shardInfer → ${usePrefix ? "fulfilResumed" : "fulfil"} → POST /tasks → verifyAndUpdate`);
    return "None";
  }
  if (!gk.isConfigured()) {
    entry.action = "skipped";
    entry.reason = "GK_API_KEY not set";
    log(`     ✗ GK_API_KEY not set — cannot request a verdict (market resolves NO at deadline+buffer if nobody else does)`);
    return "None";
  }

  let resumeRoot = null;
  if (usePrefix) {
    const st = state[m.address];
    const same = st && Array.isArray(st.prefixIds) && st.prefixIds.length === prefixIds.length && st.prefixIds.every((v, i) => v === prefixIds[i]);
    if (same && (await prefixSettled(st.prefixRoot))) {
      resumeRoot = st.prefixRoot;
      log(`     prefix ${resumeRoot} settled — resuming`);
    } else {
      if (st && !same) log(`     stored prefix ids differ from the canonical ones — re-warming`);
      resumeRoot = await warmPrefix(m, prefixIds, log, entry);
    }
  }

  let infer;
  let calldata;
  for (let attempt = 0; ; attempt++) {
    try {
      if (resumeRoot) {
        log(`     shardInfer (resume, prefix_len ${prefixLen}) …`);
        infer = await gk.shardInfer(gk.buildQwen35Request({ consumer: judgeAddress, promptIds: ids, maxNew: 1, prefixLen }));
        if (!infer.prefix_root) throw new Error("resumed infer returned no prefix_root");
        if (infer.prefix_root.toLowerCase() !== resumeRoot.toLowerCase()) throw new Error(`resumed from ${infer.prefix_root}, expected ${resumeRoot}`);
        calldata = encodeFunctionData({ abi: judgeAbi, functionName: "fulfilResumed", args: [ids, 1n, infer.answer_ids, infer.pipeline_root, infer.prefix_root] });
      } else {
        log(`     shardInfer (fresh, ${ids.length} ids) …`);
        infer = await gk.shardInfer(gk.buildQwen35Request({ consumer: judgeAddress, promptIds: ids, maxNew: 1 }));
        calldata = encodeFunctionData({ abi: judgeAbi, functionName: "fulfil", args: [ids, 1n, infer.answer_ids, infer.pipeline_root] });
      }
      break;
    } catch (e) {
      // Coordinator restarted since the warm: its prefix cache is in-memory. Re-warm once.
      if (resumeRoot && attempt === 0 && gk.isPrefixCacheMiss(e)) {
        log(`     coordinator lost the warmed prefix — re-warming`);
        resumeRoot = await warmPrefix(m, prefixIds, log, entry);
        continue;
      }
      throw e;
    }
  }
  const answer = infer.answer_ids?.[0];
  const local = QWEN35.yesIds.includes(answer) ? "Yes" : QWEN35.noIds.includes(answer) ? "No" : "None";
  entry.answerId = answer;
  entry.pipelineRoot = infer.pipeline_root;
  entry.prefixRoot = infer.prefix_root ?? null;
  log(`     answer id ${answer} (${local}) · pipeline_root ${infer.pipeline_root} · ${infer.segments} segments`);
  if (local === "None") log(`     answer is not YES/NO — the judge will reject this settlement; submitting anyway for the log`);

  await settleThroughRouter(resumeRoot ? "fulfilResumed" : "fulfil", calldata, log, entry);
  const verdict = await readVerdict(key);
  entry.verdict = verdict;
  entry.action = "requested";
  log(`     verdict now: ${verdict}`);
  return verdict;
}

// ----------------------------------------------------------------------------- main
const report = { network: networkName, dryRun, at: new Date().toISOString(), judge: judgeAddress, emails: 0, candidates: [], submitted: [], resolvedNo: [], skipped: [], judged: [] };
const lines = [];
const log = (s) => {
  console.log(s);
  lines.push(s);
};

// Email subject lines are personal data once this bot reads a real mailbox, and CI logs +
// the job summary of a PUBLIC repo are world-readable forever. Under GitHub Actions we
// therefore never print subjects or subject fingerprints there. Local runs
// (no GITHUB_ACTIONS) keep full detail for debugging.
const REDACT = !!process.env.GITHUB_ACTIONS;
const safeError = e => REDACT ? "Operation failed (details kept private)" : String(e.shortMessage ?? e.message).slice(0, 300);
const showSubject = (s) => {
  if (!REDACT) return `"${s}"`;
  return "<redacted>";
};

log(`# Settlement bot — ${networkName}${dryRun ? " (dry run)" : ""}${judgeOnly ? " (judge-only)" : ""}${noJudge ? " (no-judge)" : ""}`);
const markets = await loadMarkets();
const live = markets.filter((m) => m.resolution === 0);
const judgedLive = live.filter((m) => m.criteria !== "");
log(`${markets.length} markets, ${live.length} unresolved (${judgedLive.length} judged)`);
if (judgedLive.length && !judgeAddress) log(`no "llmJudge" in deployments/${networkName}.json — judged markets will be skipped`);
else if (judgeAddress) log(`LLMJudge ${judgeAddress} · prefix resume ${usePrefix ? "on" : "off"} · state ${statePath} · fleet ${gk.isConfigured() ? gk.GK.routerUrl : "not configured (no GK_API_KEY)"}`);

async function submitAccepted(m, si, src, proof, email) {
  log(`   ✓ checkProof ok — submitting${dryRun ? " (dry run)" : ""}`);
  try {
    const paginated = (encodeFunctionData({abi:marketAbi,functionName:"submitProof",args:[BigInt(si),proof]}).length-2)/2+200 > 128*1024;
    let r;
    if (paginated && deployment.emailBodyStore) {
      const pages = bodyPages(proof.canonicalBody), pointers = [];
      log(`   body transport: ${pages.length} public uploads plus settlement; uploaded pages are reused`);
      if (dryRun) {
        report.submitted.push({market:m.id,question:m.question,source:src.name,tx:null,transport:"paginated",pages:pages.length,resolvesYes:m.matchedCount+1>=m.threshold,finalGasUnmeasured:true});
        return; // Do not pretend the unuploaded final transaction has been simulated.
      }
      for (const page of pages) {
        const hash = keccak256(page);
        let pointer = await publicClient.readContract({address:deployment.emailBodyStore,abi:bodyStoreAbi,functionName:"chunkForHash",args:[hash]});
        if (pointer === zeroAddress) {
          const {request} = await publicClient.simulateContract({account,address:deployment.emailBodyStore,abi:bodyStoreAbi,functionName:"storeChunk",args:[page]});
          await send("store body page",request);
          pointer = await publicClient.readContract({address:deployment.emailBodyStore,abi:bodyStoreAbi,functionName:"chunkForHash",args:[hash]});
        }
        if (pointer === zeroAddress) throw new Error("Body page not confirmed; retry to resume");
        pointers.push(pointer);
      }
      const {request} = await publicClient.simulateContract({account,address:deployment.emailBodyStore,abi:bodyStoreAbi,functionName:"submitWithChunks",args:[m.address,BigInt(si),{...proof,canonicalBody:"0x"},pointers]});
      r = await send("submitWithChunks",request);
    } else {
      const { request } = await publicClient.simulateContract({ account: account ?? undefined, address: m.address, abi: marketAbi, functionName: "submitProof", args: [BigInt(si), proof] });
      r = await send("submitProof", request);
    }
    m.sourceMatched[si] = true;
    m.matchedCount++;
    report.submitted.push({ market: m.id, question: m.question, source: src.name, tx: r.hash ?? null, resolvesYes: m.matchedCount >= m.threshold });
    log(`   → proof ${dryRun ? "would be" : ""} accepted (${m.matchedCount}/${m.threshold})${m.matchedCount >= m.threshold ? " — MARKET RESOLVES YES" : ""}${r.hash ? ` tx ${r.hash}` : ""}`);
  } catch (e) {
    log(`   ✗ submit failed: ${safeError(e)}`);
    report.skipped.push({ email: email.id, market: m.id, reason: safeError(e) });
  }
}

const domains = [...new Set(live.flatMap((m) => m.sources.map((s) => s.dkimDomain)))];
const emails = await collectEmails(domains);
report.emails = emails.length;
log(`${emails.length} candidate email(s) (${emlFiles.length ? "files" : `IMAP since ${sinceSpec}`})`);

for (const email of emails) {
  if (REDACT) email.id = createHash("sha256").update(email.id).digest("hex").slice(0, 16);
  let parsed;
  try {
    parsed = parseEml(email.raw);
  } catch (e) {
    report.skipped.push({ email: email.id, reason: `unparseable: ${safeError(e)}` });
    continue;
  }
  const subj = parsed.boundSubject;
  log(`\n## ${email.id}: d=${parsed.domain} s=${parsed.selector} from=${REDACT ? "<redacted>" : parsed.fromAddress}\n   ${showSubject(parsed.subjectDisplay)}`);
  for (const m of live) {
    const judged = m.criteria !== "";
    if (judged ? noJudge : judgeOnly) continue;
    for (const [si, src] of m.sources.entries()) {
      if (src.dkimDomain !== parsed.domain || m.sourceMatched[si]) continue;
      // local mirror of the onchain checks (cheap pre-filter); judged markets have no regex
      const fromOk = !src.fromRegex || toJsRegex(src.fromRegex).test(parsed.fromAddress);
      const timeOk = parsed.timestamp >= m.windowStart && parsed.timestamp <= m.deadline;
      if (!fromOk || !timeOk) continue;
      if (!judged) {
        const pattern = src.contentRegex || m.contentRegex;
        const field = FIELD[m.contentField];
        const re = toJsRegex(pattern);
        const contentOk =
          field === "subject" ? re.test(subj) : field === "body" ? re.test(parsed.bodyExcerpt) : re.test(subj) || re.test(parsed.bodyExcerpt);
        if (!contentOk) continue;
      }

      log(`   ${judged ? "judged " : ""}market #${m.id} "${m.question.slice(0, 70)}" via ${src.name}`);
      if (judged && !judgeAddress) {
        log(`   ↷ skipped: deployment has no llmJudge address`);
        report.judged.push({ email: email.id, market: m.id, source: src.name, action: "skipped", reason: "no llmJudge in deployment" });
        continue;
      }
      const hash = await ensureKey(parsed.domain, parsed.selector, log);
      if (!hash) {
        report.skipped.push({ email: email.id, market: m.id, reason: "DKIM key unavailable" });
        continue;
      }
      let proof;
      try { proof = buildEmailProof(parsed, hash, { contentField: deployment.bodyParsingVersion === 1 ? m.contentField : 0, pattern: src.contentRegex || m.contentRegex }); }
      catch (e) { report.skipped.push({ email: email.id, market: m.id, reason: safeError(e) }); continue; }

      const proofCalldata = encodeFunctionData({ abi: marketAbi, functionName: "submitProof", args: [BigInt(si), proof] });
      if ((proofCalldata.length - 2) / 2 + 200 > 128 * 1024 && !deployment.emailBodyStore) {
        report.skipped.push({ email: email.id, market: m.id, reason: "Body proof exceeds common 128 KiB transaction relay limit" });
        continue;
      }

      if (judged) {
        const entry = { email: email.id, market: m.id, question: m.question, source: src.name, tasks: [], txs: [] };
        report.judged.push(entry);
        try {
          const [key, subjectHex, ok] = await publicClient.readContract({ address: m.address, abi: marketAbi, functionName: "promptKeyFor", args: [proof] });
          const subjectBytes = Buffer.from(subjectHex.slice(2), "hex");
          entry.key = key;
          // the JSON report is uploaded as a CI artifact on a public repo — redact there too
          entry.subject = REDACT ? showSubject(subjectBytes.toString("utf8")) : subjectBytes.toString("utf8");
          if (!ok) {
            entry.action = "skipped";
            entry.reason = "subject unreadable/unsafe";
            log(`   ✗ promptKeyFor: subject unreadable or unsafe (${showSubject(subjectBytes.toString("utf8"))})`);
            continue;
          }
          log(`   prompt key ${key} · subject "${entry.subject}"`);
          let verdict = await readVerdict(key);
          log(`   judge verdict: ${verdict}`);
          if (verdict === "None") verdict = await requestVerdict(m, key, subjectBytes, log, entry);
          else entry.action = verdict === "Yes" ? "already-yes" : "verdict-no";
          entry.verdict = verdict;
          if (verdict === "No") {
            log(`   ✗ judge says NO — this email is not evidence for market #${m.id}`);
            continue;
          }
          if (verdict !== "Yes") {
            if (!dryRun) log(`   ✗ no YES verdict after settlement — not submitting`);
            continue;
          }
        } catch (e) {
          entry.action = "error";
          entry.reason = safeError(e);
          log(`   ✗ judge path failed: ${entry.reason}`);
          continue;
        }
      }

      const [ok, reason] = await publicClient.readContract({ address: m.address, abi: marketAbi, functionName: "checkProof", args: [BigInt(si), proof] });
      report.candidates.push({ email: email.id, market: m.id, source: src.name, ok, reason });
      if (!ok) {
        log(`   ✗ checkProof: ${reason}`);
        continue;
      }
      await submitAccepted(m, si, src, proof, email);
    }
  }
}

// expired markets → NO
const now = Math.floor(Date.now() / 1000);
for (const m of judgeOnly ? [] : live) {
  if (m.matchedCount >= m.threshold) continue;
  if (now > m.deadline + m.resolutionBuffer) {
    log(`\nmarket #${m.id} past deadline+buffer — resolving NO${dryRun ? " (dry run)" : ""}`);
    try {
      const { request } = await publicClient.simulateContract({ account: account ?? undefined, address: m.address, abi: marketAbi, functionName: "resolveNo" });
      const r = await send("resolveNo", request);
      report.resolvedNo.push({ market: m.id, question: m.question, tx: r.hash ?? null });
    } catch (e) {
      log(`   ✗ resolveNo failed: ${safeError(e)}`);
    }
  }
}

log(`\n---\nemails ${report.emails} · candidate pairs ${report.candidates.length} · proofs submitted ${report.submitted.length} · resolved NO ${report.resolvedNo.length} · skipped ${report.skipped.length} · judged ${report.judged.length}`);
if (outPath) writeFileSync(outPath, JSON.stringify(report, null, 2), { mode: 0o600 });
if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, lines.join("\n") + "\n");
