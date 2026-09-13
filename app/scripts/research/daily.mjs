#!/usr/bin/env node
// Local private research runner. Does not publish mail, create markets, or send transactions.
import { existsSync, readFileSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fetchResolvedMarkets } from "./polymarket.mjs";
import { marketCheckpoint } from "./checkpoint.mjs";
import { MailStore, DEFAULT_DATA_DIR, digest, privateJson, readLargeJson } from "./store.mjs";
import { mailboxConfig, receivedEmails } from "../mailbox.mjs";
import { writeResearchReport } from "./report.mjs";

const args = process.argv.slice(2);
const opt = (name, fallback) => args.includes(`--${name}`) ? args[args.indexOf(`--${name}`) + 1] : fallback;
if (process.env.GITHUB_ACTIONS) throw new Error("Private mailbox research must run locally, never in public GitHub Actions");
process.umask(0o077);
const dir = resolve(opt("data-dir", process.env.MOP_DATA_DIR || DEFAULT_DATA_DIR));
const store = new MailStore(dir);
const lock = join(dir, "daily.lock");
let locked = false;
try {
  const existing = existsSync(lock) ? Number(readFileSync(lock, "utf8")) : null;
  if (existing) {
    let running = true;
    try { process.kill(existing, 0); } catch(e) { if (e.code === "ESRCH") running = false; }
    if (!running) rmSync(lock);
  }
  writeFileSync(lock, String(process.pid), { flag: "wx", mode: 0o600 }); locked = true;
  // Public data collection and the first all-mailbox backfill are independent.
  // Finish/persist public pagination even when years of email remain to import.
  const datasetPath = join(dir, "polymarket-latest.json");
  const checkpoint = args.includes("--cached-markets") ? null : marketCheckpoint(dir);
  const datasetOutcome = (async () => {
    const dataset = args.includes("--cached-markets")
      ? await readLargeJson(datasetPath)
      : await fetchResolvedMarkets({ now: checkpoint.now, fetcher: checkpoint.fetcher,
        onPage: p => { if (p.pages % 10 === 0) console.log(`Polymarket: ${p.scanned} closed markets scanned, ${p.matched} resolved in window; reached ${p.oldestClosedAt}`); } });
    if (!args.includes("--cached-markets")) privateJson(datasetPath, dataset);
    checkpoint?.fetched();
    console.log(`Public pagination complete: ${dataset.markets.length} resolved markets`);
    return dataset;
  })().then(dataset => ({ dataset }), error => ({ error }));
  let mailStatus = { status: "not_started", indexedMessages: store.count(), newMessages: 0, failures: 0, folders: 0, enumeratedMessages: 0, mailboxCoverage: [] };
  const saveMailProgress = () => privateJson(join(dir, "mailbox-coverage.json"), {
    ...mailStatus, indexedMessages: store.count(), updatedAt: new Date().toISOString() });
  if (args.includes("--markets-only")) mailStatus.status = "not_scanned";
  else {
    try {
      mailStatus.status = "running"; saveMailProgress();
      const config = mailboxConfig();
      const identity = digest(`${config.host}:${config.user}`);
      const previous = store.getSetting("mailboxIdentity");
      if (previous && previous !== identity) throw new Error("Use a separate data directory for another mailbox");
      store.setSetting("mailboxIdentity", identity);
      for await (const email of receivedEmails({ config, alreadyIndexed: ref => store.hasRef(ref),
        onMailbox: details => {
          mailStatus.folders++; mailStatus.enumeratedMessages += details.messages; mailStatus.mailboxCoverage.push(details); saveMailProgress();
          console.log(`Mailbox folder: ${details.messages} enumerated, ${details.pending} pending references (sent/drafts are excluded on fetch)`);
        } })) {
        try { await store.add(email); mailStatus.newMessages++; }
        catch (error) { mailStatus.failures++; store.recordFailure(email, error); }
        if ((mailStatus.newMessages + mailStatus.failures) % 100 === 0) {
          saveMailProgress(); console.log(`Mailbox: ${mailStatus.newMessages} imported, ${mailStatus.failures} failed`);
        }
      }
      mailStatus.status = mailStatus.failures ? "incomplete" : "complete";
      mailStatus.indexedMessages = store.count();
      mailStatus.completedAt = new Date().toISOString();
      mailStatus.scope = (config.mailboxes?.length ? "Explicitly selected mailboxes only. " : "All retained received messages in discovered folders, including archived, spam and trash. ") +
        "Excludes sent/drafts; attachment contents are not indexed. Provider-side IMAP limits may hide older messages.";
    } catch (error) {
      mailStatus.status = "blocked";
      // No IMAP server/credential text in console output or the report.
      mailStatus.reason = "Mailbox unavailable or not configured. Check private config and docs/EMAIL-ACCESS.md.";
      console.log(mailStatus.reason);
    }
  }
  saveMailProgress();
  const outcome = await datasetOutcome;
  if (outcome.error) throw outcome.error;
  const dataset = outcome.dataset;
  const { overview, reportPath } = writeResearchReport({ store, dataset, mailStatus,
    onProgress: p => console.log(`Research: ${p.markets} markets compared, ${p.marketsWithCandidates} with candidates; semantic review pending`) });
  checkpoint?.complete();
  console.log(JSON.stringify({ ...overview.summary, mailbox: mailStatus.status, reportPath }, null, 2));
  if (mailStatus.status !== "complete" && !args.includes("--markets-only")) process.exitCode = 2;
} finally {
  store.close();
  if (locked) rmSync(lock);
}
