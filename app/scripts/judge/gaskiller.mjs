// Gas Killer client for the judged-market settlement path (see README.md in this directory).
//
// Two HTTP surfaces:
//   * the public router ingress (`GK_ROUTER_URL`, Bearer `GK_API_KEY`): POST /tasks → task_id,
//     GET /tasks/{id} → {status, payload}. The payload is a ready-to-sign `verifyAndUpdate`
//     transaction that the CLIENT signs and broadcasts before `valid_until_block`.
//   * the sharded coordinator (`GK_SHARD_URL`, may equal the router): POST /shard/infer runs
//     one inference through k-of-N operator committees and returns answer_ids + pipeline_root;
//     POST /shard/prefix warms a prefill-only prefix and returns prefix_root + settle_calldata.
//
// Field names/types mirror service PR #321 router/src/shard.rs (InferRequest/InferResponse/
// PrefixWarmResponse) and site/openapi.yaml (GasKillerTaskRequestBody/TaskView/PayloadView).
import { hexToBytes } from "viem";

// ----------------------------------------------------------------------------- env
const env = (name, def) => (process.env[name] !== undefined && process.env[name] !== "" ? process.env[name] : def);
const envInt = (name, def) => Number(env(name, def));

export const GK = {
  routerUrl: env("GK_ROUTER_URL", "https://testnet.gaskiller.xyz").replace(/\/$/, ""),
  shardUrl: env("GK_SHARD_URL", env("GK_ROUTER_URL", "https://testnet.gaskiller.xyz")).replace(/\/$/, ""),
  apiKey: env("GK_API_KEY", ""),
  shardTimeoutMs: envInt("GK_SHARD_TIMEOUT_MS", 4 * 3600_000), // bridge.py uses 14400 s
  taskTimeoutMs: envInt("GK_TASK_TIMEOUT_MS", 30 * 60_000),
  taskPollMs: envInt("GK_TASK_POLL_MS", 5_000),
};

export const isConfigured = () => Boolean(GK.apiKey);

// ----------------------------------------------------------------------------- qwen35 pins
// Exactly bridge.py MODELS["qwen35"].req (the demo fleet's pinned Qwen3.5-35B-A3B engine v3),
// except `consumer` (ours: the LLMJudge) and seqCap (ours: 512, see rewriteSeqCap).
export const QWEN35_DEMO = {
  seg_engine: "0xcA459C95ee034D21339cd5ad7209441fD54bcd51",
  weights_root: "0x0000000000000000000000000000000000000000",
  manifest: "0x7bdf4876a6861287521dadab3d3870f74dfa557507ed200d49f75bcb09f01fa9",
  packed_config: [
    "0x0800020028100201000003ca0000400101004004080100020000000000000000",
    "0x0000000010c6f7a10000000010000000000000081527a02b0000000000000000",
    "0x002b48c60003c8ee0003c8ec2010008000800400000000000000000000000000",
  ],
  packed_config_w3: "0x0000000016a09e66000000000000000000000000000000000000000000000000",
  n_layers: 40,
  kvd: 512,
  dim: 2048,
  vocab: 248320,
  stop0: 248046, // <|im_end|>
  stop1: 248044, // <|endoftext|>
  seq_cap: 64, // demo value; rewritten to GK_QWEN35_SEQ_CAP (512) for the judge
  stages: 4, // demo value; the judge uses GK_QWEN35_STAGES (10)
  argmax_shards: 2,
};

/**
 * Packed-config word 0 carries seqCap as a 16-bit big-endian field at bits 136..151 of the
 * uint256 (= bytes 13..14 counted from the most-significant byte). The demo pins 64; our
 * prompts are ~270 ids so the judge requests 512. Returns the rewritten 0x-hex word.
 */
export function rewriteSeqCap(w0Hex, seqCap) {
  if (!Number.isInteger(seqCap) || seqCap < 1 || seqCap > 0xffff) throw new Error(`seqCap out of u16 range: ${seqCap}`);
  const b = Buffer.from(w0Hex.replace(/^0x/, ""), "hex");
  if (b.length !== 32) throw new Error("packed_config[0] must be 32 bytes");
  b[13] = (seqCap >> 8) & 0xff;
  b[14] = seqCap & 0xff;
  return `0x${b.toString("hex")}`;
}

export function readSeqCap(w0Hex) {
  const b = Buffer.from(w0Hex.replace(/^0x/, ""), "hex");
  return (b[13] << 8) | b[14];
}

/** Every model field, env-overridable as GK_QWEN35_<UPPER_SNAKE>. */
export function qwen35Config() {
  const cfg = {
    seg_engine: env("GK_QWEN35_SEG_ENGINE", QWEN35_DEMO.seg_engine),
    weights_root: env("GK_QWEN35_WEIGHTS_ROOT", QWEN35_DEMO.weights_root),
    manifest: env("GK_QWEN35_MANIFEST", QWEN35_DEMO.manifest),
    packed_config: [
      env("GK_QWEN35_PACKED_CONFIG_0", QWEN35_DEMO.packed_config[0]),
      env("GK_QWEN35_PACKED_CONFIG_1", QWEN35_DEMO.packed_config[1]),
      env("GK_QWEN35_PACKED_CONFIG_2", QWEN35_DEMO.packed_config[2]),
    ],
    packed_config_w3: env("GK_QWEN35_PACKED_CONFIG_W3", QWEN35_DEMO.packed_config_w3),
    n_layers: envInt("GK_QWEN35_N_LAYERS", QWEN35_DEMO.n_layers),
    kvd: envInt("GK_QWEN35_KVD", QWEN35_DEMO.kvd),
    dim: envInt("GK_QWEN35_DIM", QWEN35_DEMO.dim),
    vocab: envInt("GK_QWEN35_VOCAB", QWEN35_DEMO.vocab),
    stop0: envInt("GK_QWEN35_STOP0", QWEN35_DEMO.stop0),
    stop1: envInt("GK_QWEN35_STOP1", QWEN35_DEMO.stop1),
    seq_cap: envInt("GK_QWEN35_SEQ_CAP", 512),
    model: env("GK_QWEN35_MODEL", "qwen35"),
    stages: envInt("GK_QWEN35_STAGES", 10), // 40 layers / full-attention every 4 ⇒ at most 10 aligned stages
    argmax_shards: envInt("GK_QWEN35_ARGMAX_SHARDS", QWEN35_DEMO.argmax_shards),
  };
  // The on-chain packed config must agree with the request's seq_cap or the engine rejects
  // the prompt; rewrite word 0 unless the operator already pinned a custom word 0.
  if (!process.env.GK_QWEN35_PACKED_CONFIG_0) cfg.packed_config[0] = rewriteSeqCap(cfg.packed_config[0], cfg.seq_cap);
  return cfg;
}

/**
 * Build a `POST /shard/infer` / `POST /shard/prefix` InferRequest for the judge.
 * @param {{consumer:string, promptIds:number[], maxNew?:number, prefixLen?:number}} p
 */
export function buildQwen35Request({ consumer, promptIds, maxNew = 1, prefixLen }) {
  const cfg = qwen35Config();
  if (!consumer) throw new Error("consumer (LLMJudge address) required");
  if (promptIds.length + maxNew > cfg.seq_cap) {
    throw new Error(`prompt (${promptIds.length}) + max_new (${maxNew}) exceeds seq_cap ${cfg.seq_cap} (raise GK_QWEN35_SEQ_CAP)`);
  }
  if (promptIds.some((t) => t < 0 || t >= cfg.vocab)) throw new Error("token id out of vocab range");
  const req = { consumer, ...cfg, prompt_ids: promptIds, max_new: maxNew };
  if (prefixLen !== undefined && prefixLen !== null) req.prefix_len = prefixLen;
  return req;
}

// ----------------------------------------------------------------------------- http
export class GasKillerError extends Error {
  constructor(message, { status, code, body } = {}) {
    super(message);
    this.name = "GasKillerError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

async function httpJson(url, { method = "GET", body, timeoutMs = 60_000, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    if (!GK.apiKey) throw new GasKillerError("GK_API_KEY not set", { code: "UNAUTHORIZED" });
    headers.Authorization = `Bearer ${GK.apiKey}`;
  }
  const res = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  const text = await res.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = null;
  }
  if (!res.ok) {
    const code = json?.error?.code ?? null;
    const msg = json?.error?.message ?? text.slice(0, 300);
    throw new GasKillerError(`${method} ${url} → ${res.status}${code ? ` ${code}` : ""}: ${msg}`, { status: res.status, code, body: json ?? text });
  }
  return json;
}

// ----------------------------------------------------------------------------- coordinator
/** POST /shard/infer → {infer_id, answer_ids, pipeline_root, segments, prefix_root?} */
export function shardInfer(req) {
  return httpJson(`${GK.shardUrl}/shard/infer`, { method: "POST", body: req, timeoutMs: GK.shardTimeoutMs });
}

/** POST /shard/prefix → {prefix_root, prefix_len, stage_state_commitments, segments, settle_calldata} */
export function shardPrefixWarm(req) {
  return httpJson(`${GK.shardUrl}/shard/prefix`, { method: "POST", body: req, timeoutMs: GK.shardTimeoutMs });
}

/** Coordinator error text for a resume whose prefix is not in its (in-memory) cache. */
export const isPrefixCacheMiss = (e) => /warm it via POST \/shard\/prefix|prefix.*not (warmed|cached)|no warmed prefix/i.test(String(e?.message ?? e));

// ----------------------------------------------------------------------------- router tasks
/** 0x-hex calldata → byte array, the wire form `call_data` requires. */
export const calldataBytes = (hex) => Array.from(hexToBytes(hex));

/**
 * POST /tasks. `call_data` may be 0x-hex or a byte array; `value` a bigint/number/hex string.
 * transition_index omitted ⇒ "auto" (the router serialises the singleton's counter).
 * @returns {Promise<string>} task_id
 */
export async function submitTask({ target_address, from_address, call_data, value = 0n, block_height, transition_index }) {
  const body = {
    target_address,
    from_address,
    call_data: typeof call_data === "string" ? calldataBytes(call_data) : call_data,
    value: typeof value === "string" ? value : `0x${BigInt(value).toString(16)}`,
    block_height: Number(block_height),
  };
  if (transition_index !== undefined && transition_index !== null && transition_index !== "auto") body.transition_index = Number(transition_index);
  const res = await httpJson(`${GK.routerUrl}/tasks`, { method: "POST", body: { body }, auth: true });
  if (!res?.task_id) throw new GasKillerError(`POST /tasks: no task_id in response`, { body: res });
  return res.task_id;
}

/** GET /tasks/{id}; a 409 PAYLOAD_EXPIRED surfaces as GasKillerError{code:"PAYLOAD_EXPIRED"}. */
export function getTask(taskId) {
  return httpJson(`${GK.routerUrl}/tasks/${taskId}`, { auth: true });
}

export const isPayloadExpired = (e) => e?.code === "PAYLOAD_EXPIRED" || e?.status === 409;

/**
 * Poll until `ready` (returns the TaskView incl. payload) or throw on failed/expired/timeout.
 * A 409 PAYLOAD_EXPIRED is thrown as-is so the caller can resubmit the same calldata.
 */
export async function pollTask(taskId, { timeoutMs = GK.taskTimeoutMs, intervalMs = GK.taskPollMs, onStatus } = {}) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    const view = await getTask(taskId);
    if (view.status !== last) {
      last = view.status;
      onStatus?.(view);
    }
    if (view.status === "ready" && view.payload) return view;
    if (view.status === "failed" || view.status === "expired") {
      throw new GasKillerError(`task ${taskId} ${view.status}: ${view.error ?? "no reason"}`, { code: view.status.toUpperCase(), body: view });
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new GasKillerError(`task ${taskId} not ready after ${timeoutMs} ms`, { code: "POLL_TIMEOUT" });
}
