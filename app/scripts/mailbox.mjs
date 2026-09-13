import { ImapFlow } from "imapflow";
import { readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const DEFAULT_MAIL_CONFIG = join(homedir(), ".config", "means-of-prediction", "mailbox.json");

/** Credentials stay outside the public repository. Never print the returned object. */
export function mailboxConfig() {
  const path = process.env.MOP_MAIL_CONFIG || DEFAULT_MAIL_CONFIG;
  let saved = {};
  try {
    if (statSync(path).mode & 0o077) throw new Error("Mailbox config must be private: chmod 600 the config file");
    const raw = readFileSync(path, "utf8");
    try { saved = JSON.parse(raw); }
    catch { throw new Error("Mailbox config is not valid JSON (contents kept private)"); }
  } catch (e) {
    if (e.code !== "ENOENT") throw e;
  }
  const config = {
    host: process.env.IMAP_HOST || saved.host || "imap.gmail.com",
    user: process.env.GMAIL_USER || saved.user,
    pass: process.env.GMAIL_APP_PASSWORD || saved.appPassword,
    accessToken: process.env.IMAP_ACCESS_TOKEN || saved.accessToken,
    oauth: saved.oauth,
    mailboxes: saved.mailboxes,
  };
  if (!config.user || !(config.pass || config.accessToken || config.oauth?.refreshToken)) {
    throw new Error(`Mailbox access is not configured. See docs/EMAIL-ACCESS.md; config path: ${path}`);
  }
  return config;
}

export async function openMailbox(config = mailboxConfig(), Client = ImapFlow) {
  let accessToken = config.accessToken;
  if (config.oauth?.refreshToken) {
    const response = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST", signal: AbortSignal.timeout(30_000),
      body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: config.oauth.refreshToken,
        client_id: config.oauth.clientId, client_secret: config.oauth.clientSecret }),
    });
    if (!response.ok) throw new Error(`Mailbox OAuth refresh failed (HTTP ${response.status})`);
    accessToken = (await response.json()).access_token;
    if (!accessToken) throw new Error("Mailbox OAuth returned no access token");
  }
  const client = new Client({ host: config.host, port: 993, secure: true,
    tls: { rejectUnauthorized: true, minVersion: "TLSv1.2" },
    connectionTimeout: 15_000, greetingTimeout: 15_000, socketTimeout: 30_000,
    auth: accessToken ? { user: config.user, accessToken } : { user: config.user, pass: config.pass },
    logger: false, emitLogs: false });
  // No server error text in public logs (servers may echo mailbox identifiers).
  client.on("error", () => {});
  await client.connect();
  return client;
}

export function selectMailboxes(list, configured) {
  const selectable = list.filter(b => !b.flags?.has("\\Noselect"));
  if (configured?.length) {
    for (const path of configured) if (!selectable.some(b => b.path === path)) throw new Error("A configured mailbox is unavailable");
    return selectable.filter(b => configured.includes(b.path));
  }
  const all = selectable.find(b => b.specialUse === "\\All");
  // Gmail All Mail omits Spam and Trash. Include them to cover all retained received mail.
  return all ? [all, ...selectable.filter(b => ["\\Junk", "\\Trash"].includes(b.specialUse))]
    : selectable.filter(b => !["\\Sent", "\\Drafts"].includes(b.specialUse));
}

export function requireGmailCoverage(list, config) {
  if (config.host !== "imap.gmail.com" || config.mailboxes?.length) return;
  for (const flag of ["\\All", "\\Junk", "\\Trash"]) {
    if (!list.some(box => box.specialUse === flag && !box.flags?.has("\\Noselect"))) {
      throw new Error("Gmail All Mail, Spam and Trash must be visible in IMAP for full coverage. See docs/EMAIL-ACCESS.md.");
    }
  }
}

const sentOrDraft = msg => msg.flags?.has("\\Draft") || msg.labels?.has("\\Drafts") || msg.labels?.has("\\Sent");

// All Mail includes outgoing messages. Inspect flags before downloading bodies,
// so every incremental run does not fetch years of already excluded sent mail.
export async function* fetchReceivedMessages(client, uids) {
  const received = [];
  for await (const msg of client.fetch(uids, { uid: true, labels: true, flags: true }, { uid: true })) {
    if (!sentOrDraft(msg)) received.push(msg.uid);
  }
  if (!received.length) return;
  for await (const msg of client.fetch(received,
    { uid: true, source: true, labels: true, flags: true, internalDate: true }, { uid: true })) {
    if (sentOrDraft(msg)) continue; // labels can change between the two requests
    if (!msg.source) throw new Error("IMAP returned a message without its raw source");
    yield msg;
  }
}

export async function* receivedEmails({ since, searchQuery, config = mailboxConfig(), alreadyIndexed = () => false, onMailbox = () => {} } = {}) {
  const client = await openMailbox(config);
  try {
    const list = await client.list();
    requireGmailCoverage(list, config);
    for (const box of selectMailboxes(list, config.mailboxes)) {
      await client.mailboxOpen(box.path, { readOnly: true });
      const query = { ...(searchQuery || { all: true }), ...(since ? { since } : {}) };
      const uids = (await client.search(query, { uid: true })) || [];
      const prefix = `${box.path}#${client.mailbox.uidValidity}#`;
      // Import newer UIDs first without imposing a date cutoff. A first-time
      // multi-year backfill can then supply recent evidence while it continues.
      const pending = uids.filter(uid => !alreadyIndexed(`${prefix}${uid}`)).sort((a, b) => b - a);
      onMailbox({ path: box.path, messages: uids.length, pending: pending.length });
      for (let offset = 0; offset < pending.length; offset += 100) {
        for await (const msg of fetchReceivedMessages(client, pending.slice(offset, offset + 100))) {
          yield { id: `${prefix}${msg.uid}`, raw: msg.source.toString("latin1"), receivedAt: msg.internalDate };
        }
      }
    }
  } finally { await client.logout().catch(() => {}); }
}
