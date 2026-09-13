#!/usr/bin/env node
import { existsSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { mailboxConfig, receivedEmails } from "../mailbox.mjs";
import { MailStore, DEFAULT_DATA_DIR, digest, privateJson } from "./store.mjs";

// Separate NYT corpus: no mail-age cutoff, and no interference with the public
// market backfill or the all-mailbox daily research index.
if (process.env.GITHUB_ACTIONS) throw new Error("NYT mailbox research must run locally");
process.umask(0o077);
const dir = process.env.MOP_NYT_DATA_DIR || join(DEFAULT_DATA_DIR, "nyt");
const store = new MailStore(dir);
const lock = join(dir, "sync.lock");
let locked = false;
const status = { generatedAt: new Date().toISOString(), status: "not_started", newMessages: 0,
  indexedMessages: store.count(), failures: 0, folders: [],
  scope: "All retained received mail with a From header containing nytimes.com or newyorktimes.com, without an age cutoff. Sender matching is discovery only; DKIM and exact source identity must be checked before counting evidence." };
try {
  if (existsSync(lock)) {
    const pid = Number(readFileSync(lock, "utf8"));
    try { process.kill(pid, 0); }
    catch(e) { if (e.code === "ESRCH") rmSync(lock); else throw e; }
  }
  writeFileSync(lock, String(process.pid), { flag: "wx", mode: 0o600 }); locked = true;
  const config = mailboxConfig();
  const identity = digest(`${config.host}:${config.user}`);
  const previous = store.getSetting("mailboxIdentity");
  if (previous && previous !== identity) throw new Error("Use a separate NYT data directory for another mailbox");
  store.setSetting("mailboxIdentity", identity);
  if (config.mailboxes?.length) status.scope += " Limited to explicitly configured folders.";
  for await (const email of receivedEmails({ config,
    searchQuery: { or: [{ from: "nytimes.com" }, { from: "newyorktimes.com" }] },
    alreadyIndexed: ref => store.hasRef(ref),
    onMailbox: folder => { status.folders.push(folder); console.log(`NYT mailbox folder: ${folder.messages} matching messages, ${folder.pending} pending`); },
  })) {
    try { await store.add(email); status.newMessages++; }
    catch (error) { status.failures++; store.recordFailure(email, error); }
    if ((status.newMessages + status.failures) % 50 === 0) console.log(`NYT mail: ${status.newMessages} imported, ${status.failures} failed`);
  }
  status.status = status.failures ? "incomplete" : "complete";
} catch {
  status.status = "blocked";
  status.reason = "Mailbox unavailable, unconfigured, or already being synced. Check private config and folder coverage.";
  process.exitCode = 2;
} finally {
  status.indexedMessages = store.count();
  status.completedAt = new Date().toISOString();
  privateJson(join(dir, "mailbox-coverage.json"), status);
  store.close();
  if (locked) rmSync(lock);
}
if (status.status !== "complete") process.exitCode = 2;
console.log(JSON.stringify({status: status.status,indexedMessages:status.indexedMessages,newMessages:status.newMessages,failures:status.failures}));
