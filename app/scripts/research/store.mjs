import { DatabaseSync } from "node:sqlite";
import { mkdirSync, chmodSync, writeFileSync, readFileSync, openSync, writeSync, closeSync, renameSync, createReadStream } from "node:fs";
import { pipeline } from "node:stream/promises";
import { streamObject } from "stream-json/streamers/stream-object.js";
import { createHash } from "node:crypto";
import { join } from "node:path";
import { homedir } from "node:os";
import { resolve } from "node:dns/promises";
import { simpleParser } from "mailparser";
import { dkimVerify } from "mailauth/lib/dkim/verify.js";
import { parseEml } from "../../src/lib/prover.ts";

export const DEFAULT_DATA_DIR = join(homedir(), ".local", "share", "means-of-prediction");
export const digest = value => createHash("sha256").update(value).digest("hex");
export const marketFingerprint = m => digest(JSON.stringify([m.id, m.question, m.description, m.outcome, m.closedAt, m.resolutionSource]));
export async function readLargeJson(path) {
  // Parse without constructing a single V8 string containing the full archive.
  const value = Object.create(null);
  await pipeline(createReadStream(path), streamObject.withParserAsStream(), async source => {
    for await (const item of source) value[item.key] = item.value;
  });
  return { ...value };
}
export function privateJson(path, value) {
  const tmp = `${path}.${process.pid}.tmp`;
  if (Array.isArray(value.markets)) {
    // A full two-week report can exceed V8's maximum string length once mail
    // candidates are included. Serialize one market at a time, atomically.
    const { markets, ...metadata } = value;
    const fd = openSync(tmp, "w", 0o600);
    try {
      writeSync(fd, JSON.stringify(metadata, null, 2).slice(0, -1) + (Object.keys(metadata).length ? ',' : '') + '"markets":[\n');
      for (let i = 0; i < markets.length; i++) writeSync(fd, (i ? ',\n' : '') + JSON.stringify(markets[i]));
      writeSync(fd, '\n]}\n');
    } finally { closeSync(fd); }
  } else writeFileSync(tmp, JSON.stringify(value, null, 2) + "\n", { mode: 0o600 });
  renameSync(tmp, path);
  chmodSync(path, 0o600);
}

export class MailStore {
  constructor(dir = DEFAULT_DATA_DIR) {
    this.dir = dir;
    for (const path of [dir, join(dir, "raw"), join(dir, "reports")]) {
      mkdirSync(path, { recursive: true, mode: 0o700 }); chmodSync(path, 0o700);
    }
    const path = join(dir, "mail.sqlite");
    this.db = new DatabaseSync(path); chmodSync(path, 0o600);
    // The assistant reads while a backfill writes. WAL keeps those readers from
    // turning a successful MIME/DKIM import into a transient SQLITE_BUSY failure.
    this.db.exec("PRAGMA busy_timeout=5000; PRAGMA journal_mode=WAL;");
    this.db.exec(`CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, subject TEXT, body TEXT, metadata TEXT);
      CREATE TABLE IF NOT EXISTS refs(ref TEXT PRIMARY KEY, message_id TEXT);
      CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
      CREATE TABLE IF NOT EXISTS research_markets(id TEXT PRIMARY KEY, payload TEXT);
      CREATE TABLE IF NOT EXISTS import_failures(ref TEXT PRIMARY KEY, email_id TEXT, error_class TEXT, code TEXT, failed_at TEXT);
      CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED, subject, body, tokenize='porter unicode61');`);
    this.dns = new Map();
  }
  count() { return this.db.prepare("SELECT count(*) AS n FROM messages").get().n; }
  hasRef(ref) { return !!this.db.prepare("SELECT 1 FROM refs WHERE ref=?").get(ref); }
  recordFailure(email, error) {
    const bytes = Buffer.isBuffer(email.raw) ? email.raw : Buffer.from(email.raw, "latin1");
    const id = digest(bytes);
    writeFileSync(join(this.dir, "raw", `${id}.eml`), bytes, { mode: 0o600 });
    const safe = value => typeof value === "string" && /^[A-Za-z_][A-Za-z_0-9]{0,63}$/.test(value) ? value : "unknown";
    this.db.prepare("INSERT OR REPLACE INTO import_failures VALUES (?,?,?,?,?)")
      .run(email.id, id, safe(error?.name), safe(error?.code), new Date().toISOString());
  }
  getSetting(key) { return this.db.prepare("SELECT value FROM settings WHERE key=?").get(key)?.value; }
  setSetting(key, value) { this.db.prepare("INSERT OR REPLACE INTO settings VALUES (?,?)").run(key, value); }
  researchMarket(id) {
    const row = this.db.prepare("SELECT payload FROM research_markets WHERE id=?").get(String(id));
    return row ? JSON.parse(row.payload) : null;
  }
  saveResearchMarkets(markets) {
    const insert = this.db.prepare("INSERT INTO research_markets VALUES (?,?)");
    this.db.exec("BEGIN");
    try {
      this.db.exec("DELETE FROM research_markets");
      for (const market of markets) insert.run(market.id, JSON.stringify(market));
      this.db.exec("COMMIT");
    } catch(e) { this.db.exec("ROLLBACK"); throw e; }
  }
  get(id) {
    const row = this.db.prepare("SELECT * FROM messages WHERE id=?").get(id);
    return row ? { id, subject: row.subject, body: row.body, ...JSON.parse(row.metadata) } : null;
  }
  raw(id) { if (!/^[0-9a-f]{64}$/.test(id)) throw new Error("Invalid email ID"); return readFileSync(join(this.dir, "raw", `${id}.eml`)); }
  async add({ id: ref, raw, receivedAt }, resolver) {
    const bytes = Buffer.isBuffer(raw) ? raw : Buffer.from(raw, "latin1");
    const id = digest(bytes);
    if (!this.get(id)) {
      // Preserve bytes even if MIME parsing or verification cannot complete.
      writeFileSync(join(this.dir, "raw", `${id}.eml`), bytes, { mode: 0o600 });
      const mail = await simpleParser(bytes, { skipHtmlToText: false, skipImageLinks: true });
      const lookup = resolver || (async (name, type) => {
        const key = `${type}:${name}`;
        if (!this.dns.has(key)) this.dns.set(key, resolve(name, type));
        return this.dns.get(key);
      });
      let checked, verificationUnavailable = false;
      try { checked = await dkimVerify(bytes, { resolver: lookup }); }
      catch { checked = { results: [] }; verificationUnavailable = true; }
      const signatures = checked.results.map(s => ({ domain: s.signingDomain || null, selector: s.selector || null,
        algorithm: s.algo || null, format: s.format || null, result: s.status.result,
        signedHeaders: s.signingHeaders?.keys || [], bodyLengthLimited: !!s.canonBodyLengthLimited,
        checkedAt: new Date().toISOString() }));
      let proof = null;
      try {
        const parsed = parseEml(bytes.toString("latin1"));
        const signed = signatures.find(s => s.domain === parsed.domain && s.selector === parsed.selector);
        const header = Buffer.from(parsed.headerBytes).toString("latin1");
        const count = name => [...header.matchAll(new RegExp(`(?:^|\\r\\n)${name}:`, "gi"))].length;
        proof = { domain: parsed.domain, selector: parsed.selector, subject: parsed.boundSubject,
          signedAt: Number.isFinite(parsed.timestamp) ? new Date(parsed.timestamp * 1000).toISOString() : null,
          headerCandidate: signed?.result === "pass" && signed.algorithm === "rsa-sha256" &&
            (signed.format || "").startsWith("relaxed/") &&
            ["from", "subject", "date"].every(n => count(n) === 1),
          limitation: "Candidate only: key registry trust and exact onchain field/date parsing still need checkProof." };
      } catch { /* Unsupported/unsigned mail remains in the searchable archive. */ }
      const meta = { from: mail.from?.text || "", receivedAt: receivedAt ? new Date(receivedAt).toISOString() : null,
        date: mail.date && Number.isFinite(mail.date.getTime()) ? mail.date.toISOString() : null, signatures, proof, verificationUnavailable,
        attachmentCount: mail.attachments.length, attachmentTextIndexed: false };
      this.db.exec("BEGIN");
      try {
        this.db.prepare("INSERT INTO messages VALUES (?,?,?,?)").run(id, mail.subject || "", mail.text || "", JSON.stringify(meta));
        this.db.prepare("INSERT INTO search VALUES (?,?,?)").run(id, mail.subject || "", mail.text || "");
        this.db.exec("COMMIT");
      } catch(e) { this.db.exec("ROLLBACK"); throw e; }
    }
    this.db.prepare("INSERT OR REPLACE INTO refs VALUES (?,?)").run(ref, id);
    this.db.prepare("DELETE FROM import_failures WHERE ref=?").run(ref);
    return id;
  }
  search(terms, limit = 20, { metadataOnly = false } = {}) {
    if (!terms.length) return { total: 0, emails: [] };
    const query = terms.map(t => `"${t.replaceAll('"', '""')}"`).join(" OR ");
    const total = this.db.prepare("SELECT count(*) AS n FROM search WHERE search MATCH ?").get(query).n;
    const rows = this.db.prepare("SELECT id, bm25(search,0,5,1) AS score FROM search WHERE search MATCH ? ORDER BY score LIMIT ?").all(query, limit);
    const metadata = this.db.prepare("SELECT id, subject, metadata FROM messages WHERE id=?");
    return { total, emails: rows.map(row => {
      if (!metadataOnly) return { ...this.get(row.id), score: row.score };
      const email = metadata.get(row.id);
      return { id: email.id, subject: email.subject, ...JSON.parse(email.metadata), score: row.score };
    }) };
  }
  close() { this.db.close(); }
}

const STOP = new Set("will would could should shall the a an is are be been being has have had do does did of on in at by for to from and or but this that these those with as it its before after between than more less above below over under yes no market markets resolves resolve resolution price end date time et utc any if not which whether according following during until into".split(" "));
export function searchTerms(question) {
  return [...new Set((question.toLowerCase().match(/[\p{L}\p{N}]+/gu) || []).filter(t => t.length > 2 && !STOP.has(t)))];
}

// Retrieval only: a generic year or a market-template word should not retrieve
// the whole mailbox for every sports prop. Full-text inspection keeps searchTerms.
const MARKET_TEMPLATE_WORDS = new Set("win wins winner winning finish finishes week month year season september august july june january february march april may october november december monday tuesday wednesday thursday friday saturday sunday exact score other total team first second third half halftime inning innings quarter overtime round rounds map maps spread points sets games game match matches least percent margin highest lowest higher lower".split(" "));
export function marketSearchTerms(question) {
  return searchTerms(question).filter(t => !MARKET_TEMPLATE_WORDS.has(t) && !/^20\d\d$/.test(t));
}

export function evidenceCandidate(email, market) {
  const deadline = Date.parse(market.closedAt);
  const received = Date.parse(email.receivedAt);
  const signed = Date.parse(email.proof?.signedAt);
  const timely = Number.isFinite(received) && Number.isFinite(signed) && received <= deadline && signed <= deadline;
  return { emailId: email.id, subject: email.subject, receivedAt: email.receivedAt, signedAt: email.proof?.signedAt || null,
    signingDomain: email.proof?.domain || null, signedSubject: email.proof?.subject || null,
    rsaSubjectCandidate: !!email.proof?.headerCandidate && timely,
    fullBodyDkimVerified: email.signatures.some(s => s.result === "pass" && !s.bodyLengthLimited),
    knownBeforeClosure: timely, status: "needs_semantic_review",
    limitations: ["Topic retrieval is not resolution evidence.", "Review the exact event, winner, source restrictions, time window, and quoted/negated claims.",
      "The current contracts only match the signed subject; body evidence needs additional onchain body-hash verification."] };
}
