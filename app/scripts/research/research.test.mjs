import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createPublicKey } from "node:crypto";
import { fetchResolvedMarkets, resolvedMarket, parseTimestamp } from "./polymarket.mjs";
import { MailStore, evidenceCandidate, privateJson, readLargeJson } from "./store.mjs";
import { selectMailboxes, requireGmailCoverage, fetchReceivedMessages } from "../mailbox.mjs";
import { signEml } from "../dkim.mjs";
import { marketCheckpoint } from "./checkpoint.mjs";

const now = Date.parse("2026-09-09T12:00:00Z"), since = now - 14 * 86400000;
const market = (id, changes = {}) => ({ id, question: "Did the Fed cut interest rates?", description: "Official cut announced by September 8",
  closed: true, closedTime: "2026-09-08 12:00:00+00", endDate: "2026-07-01T00:00:00Z",
  umaResolutionStatus: "resolved", outcomes: '["Yes","No"]', outcomePrices: '["1","0"]', ...changes });

test("failed scans resume cached cursor pages with their original window", async () => {
  const dir = mkdtempSync(join(tmpdir(), "mop-checkpoint-"));
  let firstCalls = 0, fail = true;
  const fetcher = async url => {
    if (!url.includes("after_cursor")) { firstCalls++; return { ok: true, status: 200, json: async () => ({ markets: [market("1")], next_cursor: "next" }) }; }
    if (fail) return { ok: false, status: 422 };
    return { ok: true, status: 200, json: async () => ({ markets: [market("2", { closedTime: "2026-08-01T00:00:00Z" })] }) };
  };
  try {
    let checkpoint = marketCheckpoint(dir, { now, fetcher });
    await assert.rejects(fetchResolvedMarkets(checkpoint), /incomplete/);
    fail = false;
    checkpoint = marketCheckpoint(dir, { now: now + 60000, fetcher });
    const report = await fetchResolvedMarkets(checkpoint);
    assert.equal(report.markets.length, 1);
    assert.equal(firstCalls, 1);
    assert.equal(report.fetchedAt, new Date(now).toISOString());
    checkpoint.fetched();
    const publicDone = JSON.parse(readFileSync(join(dir, "polymarket-pages", "manifest.json")));
    assert.equal(publicDone.publicPaginationComplete, true);
    assert.equal(publicDone.complete, false); // mailbox/report completion is separate
    checkpoint.complete();
    assert.equal(marketCheckpoint(dir, { now: now + 120000, fetcher }).now, now + 120000);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("large reports stream on write/read and support indexed inspection", async () => {
  const dir = mkdtempSync(join(tmpdir(), "mop-report-"));
  const store = new MailStore(dir);
  try {
    const rows = [market("1"), market("2")];
    const path = join(dir, "report.json");
    for (const data of [{ markets: rows }, { note: "Report", markets: rows }, { markets: [] }]) {
      privateJson(path, data);
      assert.deepEqual(JSON.parse(readFileSync(path, "utf8")), data);
      assert.deepEqual(await readLargeJson(path), data);
      writeFileSync(path, JSON.stringify(data, null, 2));
      assert.deepEqual(await readLargeJson(path), data);
    }
    writeFileSync(path, '{"markets":[{"broken":');
    await assert.rejects(readLargeJson(path));
    store.saveResearchMarkets(rows);
    assert.deepEqual(store.researchMarket("2"), rows[1]);
    assert.equal(store.researchMarket("unknown"), null);
  } finally { store.close(); rmSync(dir, { recursive: true }); }
});

test("resolution window uses closure, not old scheduled end date, and rejects merely closed", () => {
  assert.equal(resolvedMarket(market("1"), since, now).outcome, "Yes");
  assert.equal(parseTimestamp("2026-09-08 12:00:00+00"), Date.parse("2026-09-08T12:00:00Z"));
  assert.equal(resolvedMarket(market("1", { umaResolutionStatus: "proposed" }), since, now), null);
  assert.equal(resolvedMarket(market("1", { outcomePrices: '["0.5","0.5"]' }), since, now), null);
  assert.equal(resolvedMarket(market("1", { closedTime: "2026-08-01T00:00:00Z" }), since, now), null);
});
test("cursor pagination includes short pages and stops only after cutoff or missing cursor", async () => {
  const urls = [];
  const pages = [{ markets: [market("1")], next_cursor: "a" }, { markets: [market("2")], next_cursor: "b" },
    { markets: [market("3", { closedTime: "2026-08-01T00:00:00Z" })] }];
  const r = await fetchResolvedMarkets({ now, fetcher: async url => { urls.push(url); return { ok: true, json: async () => pages.shift() }; } });
  assert.equal(r.markets.length, 2); assert.equal(r.coverage.pages, 3);
  assert.match(urls[1], /after_cursor=a/); assert.ok(urls.every(u => !u.includes("offset=")));
});
test("repeated pages and HTTP errors cannot report complete coverage", async () => {
  await assert.rejects(fetchResolvedMarkets({ now, fetcher: async () => ({ ok: true, json: async () => ({ markets: [market("1")], next_cursor: "same" }) }) }), /repeated/);
  await assert.rejects(fetchResolvedMarkets({ now, fetcher: async () => ({ ok: false, status: 422 }) }), /incomplete/);
});
test("transport and body timeouts retry the same cursor with a bounded budget", async () => {
  const urls = [], delays = [];
  const timeout = () => new DOMException("Timed out", "TimeoutError");
  const result = await fetchResolvedMarkets({ now, delay: async ms => delays.push(ms), fetcher: async url => {
    urls.push(url);
    if (urls.length === 1) throw timeout();
    if (urls.length === 2) return { ok: true, json: async () => { throw timeout(); } };
    return { ok: true, json: async () => ({ markets: [market("1")] }) };
  } });
  assert.equal(new Set(urls).size, 1);
  assert.deepEqual(delays, [1000, 2000]);
  assert.equal(result.coverage.pages, 1);
  assert.equal(result.markets.length, 1);
  let attempts = 0;
  await assert.rejects(fetchResolvedMarkets({ now, delay: async () => {}, fetcher: async () => {
    attempts++; throw timeout();
  } }), { name: "TimeoutError" });
  assert.equal(attempts, 4);
});
test("Gmail coverage includes All Mail, Spam and Trash, no INBOX-only fallback", () => {
  const list = [{ path: "Archive", specialUse: "\\All" }, { path: "Spam", specialUse: "\\Junk" },
    { path: "Bin", specialUse: "\\Trash" }, { path: "INBOX" }];
  assert.deepEqual(selectMailboxes(list).map(b => b.path), ["Archive", "Spam", "Bin"]);
  assert.throws(() => selectMailboxes(list, ["missing"]));
  assert.doesNotThrow(() => requireGmailCoverage(list, { host: "imap.gmail.com" }));
  assert.throws(() => requireGmailCoverage([{ path: "INBOX" }], { host: "imap.gmail.com" }), /visible in IMAP/);
});
test("sent and draft bodies are skipped before download and labels are rechecked", async () => {
  const calls = [];
  const client = { async *fetch(uids, query) {
    calls.push({ uids, query });
    if (!query.source) {
      yield { uid: 1 };
      yield { uid: 2, labels: new Set(["\\Sent"]) };
      yield { uid: 3, flags: new Set(["\\Draft"]) };
      yield { uid: 4 };
    } else {
      yield { uid: 1, source: Buffer.from("received") };
      yield { uid: 4, source: Buffer.from("now sent"), labels: new Set(["\\Sent"]) };
    }
  } };
  const received = [];
  for await (const m of fetchReceivedMessages(client, [1, 2, 3, 4])) received.push(m.uid);
  assert.deepEqual(received, [1]);
  assert.equal(calls[0].query.source, undefined);
  assert.deepEqual(calls[1].uids, [1, 4]);
  assert.equal(calls.length, 2);
  const sentOnly = { async *fetch(_uids, query) {
    assert.equal(query.source, undefined);
    yield { uid: 2, labels: new Set(["\\Sent"]) };
  } };
  for await (const _m of fetchReceivedMessages(sentOnly, [2])) assert.fail("Unexpected received message");
  const missing = { async *fetch() { yield { uid: 1 }; } };
  await assert.rejects(async () => { for await (const _m of fetchReceivedMessages(missing, [1])) {} }, /without its raw source/);
});
test("real signed full email is indexed once, tampering and late mail cannot become subject evidence", async () => {
  const dir = mkdtempSync(join(tmpdir(), "mop-research-"));
  const store = new MailStore(dir);
  try {
    const key = createPublicKey(readFileSync(new URL("../../../keys/dev-dkim.pub", import.meta.url)));
    const p = key.export({ format: "der", type: "spki" }).toString("base64");
    const resolver = async () => [[`v=DKIM1; k=rsa; p=${p}`]];
    const raw = signEml("From: News <news@example.com>\r\nTo: user@example.net\r\nSubject: Fed cuts rates\r\nDate: Tue, 08 Sep 2026 10:00:00 +0000\r\n\r\n" + "News ".repeat(1200) + "unusualneedle", { domain: "example.com" });
    const id = await store.add({ id: "archive#1#1", raw, receivedAt: "2026-09-08T10:01:00Z" }, resolver);
    await store.add({ id: "label#1#4", raw, receivedAt: "2026-09-08T10:01:00Z" }, resolver);
    assert.equal(store.count(), 1); assert.equal(store.hasRef("label#1#4"), true);
    assert.equal(store.search(["unusualneedle"]).total, 1); // beyond old 4096-byte excerpt
    assert.equal(statSync(join(dir, "mail.sqlite")).mode & 0o077, 0);
    const email = store.get(id);
    assert.equal(email.signatures[0].result, "pass");
    assert.equal(email.proof.headerCandidate, true);
    const m = resolvedMarket(market("1"), since, now);
    assert.equal(evidenceCandidate(email, m).rsaSubjectCandidate, true);
    assert.equal(evidenceCandidate({ ...email, receivedAt: "2026-09-09T10:00:00Z" }, m).rsaSubjectCandidate, false);
    const changed = await store.add({ id: "archive#1#2", raw: raw.replace("unusualneedle", "tampered"), receivedAt: "2026-09-08T10:01:00Z" }, resolver);
    assert.equal(store.get(changed).proof.headerCandidate, false);
    const pending = { id: "archive#1#3", raw, receivedAt: "2026-09-08T10:01:00Z" };
    store.recordFailure(pending, { name: "TypeError", code: "server could echo private text" });
    assert.equal(store.db.prepare("SELECT code FROM import_failures WHERE ref=?").get(pending.id).code, "unknown");
    await store.add(pending, resolver);
    assert.equal(store.db.prepare("SELECT count(*) n FROM import_failures").get().n, 0);
  } finally { store.close(); rmSync(dir, { recursive: true }); }
});
