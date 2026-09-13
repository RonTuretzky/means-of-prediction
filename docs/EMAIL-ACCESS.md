# Email access and automatic settlement

The app needs **raw RFC 822 messages**, including their DKIM-Signature and signed headers. A Gmail search connector that returns only readable text is not sufficient for cryptographic settlement. Reading and analyzing your mailbox does not require a wallet key.

## Connect Gmail once

**Local setup completed September 9, 2026:** the supplied Gmail account is authenticated, its private configuration is saved outside the repository with owner-only permissions, and the NYT archive has been imported through read-only IMAP. No additional mailbox setup command is needed on this Mac. This enables local research. The separate DigitalOcean settlement worker described below now uses a protected copy of this configuration for continuous NYT intake.

The easiest setup, after creating a Google app password, is to run `pnpm mailbox:setup` from `app/` in your terminal. It prompts for the address, hides password entry, verifies read access and saves the private configuration. It refuses to overwrite an existing config. For manual setup or OAuth, follow the steps below.

1. Enable Google Account **2-Step Verification**.
2. Create an **App password** named “Means of Prediction” at https://myaccount.google.com/apppasswords. Google may hide this option for managed accounts, security-key-only setups or Advanced Protection.
3. Create a private configuration outside the public repository:

   ```sh
   mkdir -p ~/.config/means-of-prediction
   chmod 700 ~/.config/means-of-prediction
   cp docs/mailbox.example.json ~/.config/means-of-prediction/mailbox.json
   chmod 600 ~/.config/means-of-prediction/mailbox.json
   ```

4. Edit that private file and replace `user` and `appPassword` with your account and generated app password. Do not put the secret in chat, a commit, a shell command argument or the app frontend.
5. From `app/`, run `pnpm research:daily`. The first run enumerates all accessible received mail without an age cutoff. Later runs reuse the private index and fetch new messages. Missing credentials, failed folders and failed parses are reported as incomplete access, never successful zero coverage.

The default Gmail scan includes **All Mail, Spam and Trash**, including archived mail. Sent messages and drafts are excluded. Other IMAP providers use all selectable folders except Sent/Drafts. Optional `mailboxes` in the config restricts the scope explicitly; it is no longer an all-mailbox scan. Permanently deleted mail is unavailable. Attachments are counted but their contents are not indexed. The mailbox opens read-only and messages are fetched without marking them read.

In Gmail settings, make **All Mail, Spam and Trash visible in IMAP**, and turn off any **Folder Size Limits** that hide older messages. The runner fails the full Gmail scan if these folders are missing, and records the folders and counts it can see. IMAP cannot prove that provider-hidden messages do not exist.

Google recommends OAuth when available. For an existing Gmail IMAP OAuth integration, replace `appPassword` with:

```json
"oauth": {
  "clientId": "your OAuth client ID",
  "clientSecret": "your OAuth client secret",
  "refreshToken": "your offline refresh token"
}
```

The runner refreshes access tokens each connection. Gmail **IMAP** requires the `https://mail.google.com/` OAuth scope; a `gmail.readonly` Gmail API token does not authorize IMAP. A Google Workspace administrator may need to allow the integration. Short-lived `accessToken` is also supported, but will expire and is unsuitable for unattended operation. App passwords avoid creating your own OAuth client when your account permits them.

Sources: [Google app passwords](https://support.google.com/mail/answer/185833), [Gmail IMAP OAuth](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol).

## What runs each day

The Codex automation **Daily email market coverage** wakes the current task at **09:30 America/New_York**. It runs locally with the configured mailbox, reviews the resulting candidates, and reports meaningful findings or an access failure. Keep the Mac available and Codex running for this local automation. Raw messages, full-text SQLite index and reports remain in `~/.local/share/means-of-prediction/`, with private file permissions. The content used in the assistant's semantic review is processed in this Codex task; “local storage” does not mean that model review runs offline.

This research job does not send emails, trade, create markets or submit proof transactions.

For the separately requested NYT-only archive, run `pnpm research:nyt` from `app/`. It searches all retained received NYT mail without an age cutoff and stores it under the private `nyt/` subdirectory. After a completed public market crawl, `pnpm research:nyt-candidates` compares every qualifying market with this corpus. The resulting candidate score is only a retrieval aid, never the settlement percentage. See DAILY-RESEARCH.md for the audit rules.

## Continuous automatic settlement

The dedicated DigitalOcean worker runs independently of this Mac. It polls the retained received NYT archive every minute, catches up using a durable IMAP UID cursor, and submits accepted proofs to the **new Sepolia factory**. The Gmail configuration and encryption keys were installed privately; no additional mailbox commands are needed for the configured account. See [AUTO-SETTLEMENT.md](AUTO-SETTLEMENT.md) for its deployment, health checks, signer limits, test receipts and recovery procedure.

Collection covers All Mail, Spam and Trash, with no age cutoff, but fetches message bodies only for NYT sender candidates. It rejects sent/draft messages, out-of-scope signing domains, invalid DKIM and messages above its intake size bound. This authenticated intake is separate from the broader local research index. Gmail access failure is reported as unhealthy. Permanently deleted mail and inaccessible historical DNS keys cannot be recovered by the worker.

For an eligible market, the worker checks the declared source, signed date window, exact Subject/body regex, registered DKIM key and authoritative onchain `checkProof` before sending transactions. It waits for confirmation and resumes interrupted body uploads. It never infers NO from a missing email. Unsupported body formats, unknown registry keys, insufficient gas funds and proof failures need operator attention; they are not successful settlements.

The relay key is held by a separate restricted signer. It can submit evidence and immutable body pages only, with bounded gas and a daily reservation budget. It cannot trade, withdraw, register keys or resolve NO. The original mainnet contracts and existing public site are not migrated by this worker deployment.

Accepted Subject proofs publish the signed headers and signature. Accepted **Body proofs publish the complete canonical email body**, even when the matching witness is short. Headers may contain recipient identifiers. Pagination preserves this disclosure and increases total upload cost; it is not a privacy or verification-compression mechanism. Stored mailbox messages and signed transaction journals are encrypted at rest, but the running collector necessarily decrypts them. Its operator and cloud host remain trusted.

The old Actions settlement schedule has been replaced **in the worktree** with a manual dry-run diagnostic. That workflow change reaches GitHub only when the coordinated release is pushed; the existing remote workflow has no mailbox credentials and is dormant. No mailbox or signing credentials were added to GitHub Actions.
