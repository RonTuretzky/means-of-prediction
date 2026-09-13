#!/usr/bin/env node
import { createInterface } from "node:readline/promises";
import { Writable } from "node:stream";
import { existsSync, mkdirSync, chmodSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { DEFAULT_MAIL_CONFIG, openMailbox } from "./mailbox.mjs";

// Run interactively yourself. Password entry is hidden and never appears in argv,
// shell history, console logs, the repository or the browser application.
if (!process.stdin.isTTY) throw new Error("Run pnpm mailbox:setup in an interactive terminal");
const path = process.env.MOP_MAIL_CONFIG || DEFAULT_MAIL_CONFIG;
if (existsSync(path)) throw new Error(`A configuration already exists. Edit that private file instead: ${path}`);
const normal = createInterface({ input: process.stdin, output: process.stdout });
const user = (await normal.question("Gmail address: ")).trim();
normal.close();
if (!user.includes("@")) throw new Error("Enter your full Gmail address");
process.stdout.write("Google app password (hidden): ");
const hidden = createInterface({ input: process.stdin, terminal: true,
  output: new Writable({ write(_chunk, _encoding, callback) { callback(); } }) });
const appPassword = (await hidden.question("")).replace(/\s+/g, "");
hidden.close();
process.stdout.write("\nChecking read access…\n");
if (!appPassword) throw new Error("No app password entered");
try {
  const client = await openMailbox({ host: "imap.gmail.com", user, pass: appPassword });
  try { await client.mailboxOpen("INBOX", { readOnly: true }); }
  finally { await client.logout().catch(() => {}); }
} catch {
  console.error("Gmail access failed. Check the app password, 2-Step Verification and any Workspace restrictions. Nothing was saved.");
  process.exit(1);
}
process.umask(0o077);
mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
chmodSync(dirname(path), 0o700);
writeFileSync(path, JSON.stringify({ host: "imap.gmail.com", user, appPassword }, null, 2) + "\n", { flag: "wx", mode: 0o600 });
console.log(`Verified Gmail read access and saved private configuration at ${path}. Run pnpm research:daily for the first full scan.`);
