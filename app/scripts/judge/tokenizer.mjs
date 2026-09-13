// Canonical judge tokenizer — the off-chain mirror of contracts/src/judge/TokenTable.sol.
//
// Greedy longest-match over the raw-bytes token table (ties → lowest id), restricted to ids
// below `specialBase` (no control tokens), piecewise over the prompt: ids =
//   scaffoldPrefix ++ greedy(prefixText) ++ greedy(tailText) ++ scaffoldSuffix
// exactly as LLMJudge.canonicalPromptIds computes inside the operators' simulation. The
// table is the engine-v3 tokenizer blob (tools/qwen3_convert.py build_tokenizer_blob):
//   [u8 type=1][u32 vocab][u32 stringsLen][(vocab+1) x u32 offsets][strings]
// Differentially tested against the Solidity implementation in contracts/test/LLMJudge.t.sol.
import { readFileSync } from "node:fs";

export const CHUNK = 24_575;

export function loadTable(path) {
  const buf = readFileSync(path);
  if (buf[0] !== 1) throw new Error("token table: bad type byte");
  const vocab = buf.readUInt32BE(1);
  const stringsLen = buf.readUInt32BE(5);
  const base = 9 + (vocab + 1) * 4;
  if (buf.length !== base + stringsLen) throw new Error("token table: length mismatch");
  const offs = new Uint32Array(vocab + 1);
  for (let i = 0; i <= vocab; i++) offs[i] = buf.readUInt32BE(9 + i * 4);
  return { buf, vocab, base, offs };
}

export function tokenBytes(table, id) {
  if (id >= table.vocab) throw new Error(`token id ${id} out of range`);
  return table.buf.subarray(table.base + table.offs[id], table.base + table.offs[id + 1]);
}

export function detokenize(table, ids) {
  return Buffer.concat(ids.map((id) => tokenBytes(table, id)));
}

/** Build the first-byte bucket index once per (table, specialBase). */
export function buildIndex(table, specialBase) {
  const limit = Math.min(specialBase, table.vocab);
  const buckets = Array.from({ length: 256 }, () => []);
  for (let id = 0; id < limit; id++) {
    const so = table.offs[id];
    const eo = table.offs[id + 1];
    if (eo === so) continue;
    buckets[table.buf[table.base + so]].push(id); // increasing id order within a bucket
  }
  return { table, buckets };
}

/** Greedy longest-match tokenization of `bytes` (Buffer). Ties → lowest id. */
export function greedyTokenize(index, bytes) {
  const { table, buckets } = index;
  const out = [];
  let p = 0;
  while (p < bytes.length) {
    let bestLen = 0;
    let bestId = 0;
    const remaining = bytes.length - p;
    for (const id of buckets[bytes[p]]) {
      const so = table.offs[id];
      const len = table.offs[id + 1] - so;
      if (len <= bestLen || len > remaining) continue;
      if (bytes.compare(table.buf, table.base + so, table.base + so + len, p, p + len) === 0) {
        bestLen = len;
        bestId = id;
      }
    }
    if (bestLen === 0) throw new Error(`untokenizable byte at ${p}`);
    out.push(bestId);
    p += bestLen;
  }
  return out;
}

// ---- the prompt template (mirror of contracts/src/judge/JudgePrompt.sol; keep in sync) ----
export const P0 = "You are the resolver of a prediction market.\nMarket question: ";
export const P1 = "\nResolution rules: ";
export const P2 = "\n\nA newspaper has sent a breaking-news alert email. Its subject line is:\n\"";
export const P3 =
  "\"\n\nJudging ONLY this subject line and the rules: does this email establish that " +
  "the market resolves YES? Answer with exactly one word, YES or NO.";

export const prefixText = (question, criteria) => Buffer.from(P0 + question + P1 + criteria + P2, "utf8");
export const tailText = (subjectBytes) => Buffer.concat([Buffer.from(subjectBytes), Buffer.from(P3, "utf8")]);
export const userText = (question, criteria, subjectBytes) => Buffer.concat([prefixText(question, criteria), tailText(subjectBytes)]);

/**
 * Canonical prompt ids for a judged market + signed subject.
 * @returns {{ids:number[], prefixLen:number, prefixIds:number[]}} prefixIds = scaffoldPrefix ++ greedy(prefixText)
 */
export function canonicalPromptIds(index, scaffold, question, criteria, subjectBytes) {
  const pre = greedyTokenize(index, prefixText(question, criteria));
  const tail = greedyTokenize(index, tailText(subjectBytes));
  const prefixIds = [...scaffold.prefix, ...pre];
  const ids = [...prefixIds, ...tail, ...scaffold.suffix];
  return { ids, prefixLen: prefixIds.length, prefixIds };
}

/** Qwen3.5-35B-A3B chat scaffold (thinking disabled) and answer ids — pinned constants. */
export const QWEN35 = {
  scaffold: {
    prefix: [248045, 846, 198], // <|im_start|>user\n
    suffix: [248046, 198, 248045, 74455, 198, 248068, 271, 248069, 271], // <|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n
  },
  specialBase: 248044, // <|endoftext|>; every added/control token is >= this
  yesIds: [13602, 9175, 9405, 13677, 7179, 9542], // YES Yes yes ' YES' ' Yes' ' yes'
  noIds: [8725, 2665, 2083, 5486, 2233, 874], // NO No no ' NO' ' No' ' no'
  vocab: 248320,
  tokenizerLength: 2836777,
  tokenizerChunks: 116,
  weightChunks: 1412601, // ceil(34,714,656,811 / 24,575) from the packed config's weightLen
};

// CLI: node tokenizer.mjs <table.bin> ids <utf8 text>   |   node tokenizer.mjs <table.bin> prompt <q> <criteria> <subject>
if (import.meta.url === `file://${process.argv[1]}`) {
  const [, , tablePath, mode, ...rest] = process.argv;
  const index = buildIndex(loadTable(tablePath), QWEN35.specialBase);
  if (mode === "ids") {
    console.log(JSON.stringify(greedyTokenize(index, Buffer.from(rest.join(" "), "utf8"))));
  } else if (mode === "ids-hex") {
    console.log(JSON.stringify(greedyTokenize(index, Buffer.from(rest[0].replace(/^0x/, ""), "hex"))));
  } else if (mode === "prompt-abi") {
    // ffi mode for contracts/test/LLMJudge.t.sol: arg = abi.encode(string q, string criteria, bytes subject);
    // output = abi.encode(uint32[] ids). Hand-rolled ABI so CI's forge test needs no node_modules.
    const hex = rest[0].replace(/^0x/, "");
    const word = (i) => BigInt("0x" + hex.slice(i * 64, i * 64 + 64));
    const dyn = (off) => {
      const len = Number(word(off / 32));
      return Buffer.from(hex.slice((off + 32) * 2, (off + 32) * 2 + len * 2), "hex");
    };
    const q = dyn(Number(word(0))).toString("utf8");
    const c = dyn(Number(word(1))).toString("utf8");
    const subj = dyn(Number(word(2)));
    const { ids } = canonicalPromptIds(index, QWEN35.scaffold, q, c, subj);
    const w = (n) => BigInt(n).toString(16).padStart(64, "0");
    process.stdout.write("0x" + w(32) + w(ids.length) + ids.map(w).join(""));
  } else if (mode === "prompt") {
    const [q, c, subj] = rest;
    console.log(JSON.stringify(canonicalPromptIds(index, QWEN35.scaffold, q, c, Buffer.from(subj, "utf8"))));
  } else {
    console.error("usage: tokenizer.mjs <table.bin> ids|ids-hex|prompt ...");
    process.exit(1);
  }
}
