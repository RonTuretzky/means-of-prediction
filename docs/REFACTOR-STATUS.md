> **September 10 automation update:** The dedicated DigitalOcean email worker now handles authenticated NYT intake and accepted Subject/body proof submission on the fresh Sepolia deployment, with an encrypted durable journal and restricted signer. See [AUTO-SETTLEMENT.md](AUTO-SETTLEMENT.md) for current activation status and validation; this supersedes older statements below that continuous collection still needs to be configured. Mainnet migration and coordinated frontend publication remain separate.

# Refactor status — updated 2026-09-10

This note supplements the earlier HANDOFF.md. The shared worktree already contained uncommitted soundness and LLM-judge changes; those were preserved. No commits or pushes were made. The earlier refactor did not deploy live contracts; the subsequently authorized body-parsing work deployed a fresh Sepolia stack (details below). In the subsequent authorized mailbox setup, credentials were saved privately outside the repository and NYT mail was imported through read-only IMAP.

## Body parsing and pagination — September 10 update

New contracts authenticate the complete canonical body against signed `bh=`, decode a bounded source window, and match a substring regex. Browser/bot support paginated uploads through `EmailBodyStore`; legacy subject-only ABI behavior remains gated by deployment metadata. See [BODY-PARSING.md](BODY-PARSING.md) for exact limits, addresses, receipts and costs.

Validation: 170 Foundry tests, 10 browser lifecycles, 7 body-parser Node tests, real NYT local settlement/redemption/fee lifecycles, and public synthetic direct + >128 KiB paginated lifecycles on Sepolia passed. Each of the ten featured slideshow regexes was checked against its real authenticated body with the Solidity matcher locally. No original Polymarket contracts were settled.

Backlog issues [#1](https://github.com/RonTuretzky/means-of-prediction/issues/1) and [#2](https://github.com/RonTuretzky/means-of-prediction/issues/2) document sizing and the proposed GasKiller integration; #2 tags `@tbsoc` and `@nomoregas`. The new Sepolia manifest supersedes prior stale-address warnings. Gnosis contracts and the hosted site remain unchanged; the new Sepolia factory has no LLM judge.

## Earlier refactor baseline

- Renamed `contracts/src/zkemail/` to `contracts/src/dkim/` and `IZKEmailVerifier` to `IDKIMVerifier`. Removed the unused ZK circuit scripts, verifier registry, generated assets and SnarkJS/Circom dependencies from the app. Updated product language and current architecture docs.
- Preserved the signed Subject/Date/body-excerpt soundness fixes. Added registrar-only DKIM key authorization and permanent revocation. Arbitrary public key/domain registration did not establish newspaper identity; this new registry explicitly trusts the deployer to authenticate DNS keys.
- Added a default 1% platform fee alongside LP fees. Quotes include both; treasury credit is isolated from LP credit. UI shows the fee breakdown and can trigger treasury payment. New factory/pool constructor and initialization arguments are reflected in deploy/verification scripts.
- Added private all-mailbox IMAP ingestion, incremental raw-email/SQLite storage, full-text search and real DKIM verification, plus trailing-14-day Polymarket cursor pagination and a structured semantic review interface. See DAILY-RESEARCH.md for the distinction between candidates, semantic findings and actual onchain validation.
- Created the active Codex heartbeat `daily-email-market-coverage` for 09:30 America/New_York, attached to the current task. It runs locally and stays quiet on unchanged/non-actionable state.
- Updated the existing settlement bot's mailbox discovery, avoided From/DKIM-domain filtering misses, chunked registry log requests and improved public-log redaction. Its existing GitHub schedule remains 13:17 UTC.

Validation: **152 Foundry tests**, **9 Playwright browser flows** (including actual fee accrual/treasury withdrawal) and **7 Node research tests** passed. Production build succeeded. The browser harness now names the deploy contract explicitly, syncs addresses after deployment and waits for loaded balances.

September 10 research-run improvements: public collection and mailbox backfill now run concurrently; imports prioritize recent mail while retaining full-history coverage. The comparison writer enriches one market at a time, stores compact candidate references and publishes the latest report through a private hardlink. Raw messages survive import failures, sanitized failure records support retry, and SQLite WAL permits concurrent inspection. Network and response-body timeouts retry the same cursor up to four attempts before leaving the scan incomplete. Mailbox ingestion checks flags before downloading bodies, avoiding repeated downloads of sent/draft messages from Gmail All Mail. **10 Node research tests** now pass, including rollback, concurrent-reader, timeout-retry and sent/draft exclusion checks. A **100,000-market / 2,000,000-candidate** report completed under a **192 MiB Node heap limit**. The earlier contract/browser/build results above are the September 9 baseline; this research-only update did not rerun those unrelated suites.

The first live Polymarket scan exceeded 418,000 markets and reached report serialization, where the older in-flight writer exceeded V8's string limit. The corrected reader/writer passed a **610 MB / 300,000 synthetic-market roundtrip**. Added persistent cursor-page checkpoints and verified interruption/resume behavior. The replacement live backfill **completed 4,188 pages / 418,800 scanned records**, yielding **412,964 final-winner contracts** in the fixed August 26–September 9 window. It excluded 5,748 non-0/1/invalid payouts and 88 boundary records. Its all-mailbox report retains the access failure observed when that process began, before credentials were configured; that historical status must not override the subsequently successful, separate NYT import and audit. A complete public download and mailbox import still do not imply exhaustive semantic review.

The September 10 run subsequently **completed the full retained received-mail import with zero outstanding failures** and compared every eligible market against that index. Its fresh public window, August 27 13:38:58.634 UTC through September 10 13:38:58.634 UTC, contains **418,944 final-winner contracts** from **424,700 scanned records**; 5,720 split/invalid final payouts and 36 boundary records were excluded. An interrupted network request resumed the same checkpointed window. Bounded reuse of identical retrieval queries improved report throughput while preserving each market's distinct timing checks. Private semantic findings and their limitations are in the daily and NYT reports; the complete candidate scan is not an exhaustive semantic audit.

## Activation still required

1. Mailbox access is connected, and both the full retained received-mail archive and separate NYT sender archive have been imported without an age cutoff. The NYT audit lives in the private `nyt/` data directory; its factual matches, timing and pending semantic reviews must not be conflated with proof acceptance or machine retrieval candidates. The daily automation includes the NYT-only coverage report.
2. Coordinate/land the existing uncommitted LLM-judge work as required by the earlier handoff before committing a coherent build. The new Sepolia metadata now points to runtime-verified body-parsing contracts; the earlier stale-address warning applies only to the preserved historical manifest.
3. Choose the production treasury and fee, deploy fresh contracts, verify code/addresses, register real DNS keys as the registrar, and create evidence-backed markets with explicit supported content rules. Existing clones cannot gain the new verifier, key authorization or fees.
4. Validate a complete initial mailbox scan covering each open market's full window, then enable the hosted settler's secrets. Longer outages need a catch-up scan before automatic NO resolution.

## Preservation and outputs

- Pre-refactor source snapshot and baseline diff: `/Users/wk/mop-refactor-backup-20260909/`.
- Removed unused ZK experiment and generated assets: `removed-zk/` inside that private backup.
- Private runtime data and reports: `/Users/wk/.local/share/means-of-prediction/`.
- The pre-test `contracts/deployments/local.json` was restored from the snapshot; the test chain is temporary. That was the earlier refactor baseline; the September 10 body work subsequently replaced Sepolia metadata after successful public tests.

The original handoff's claims of permissionless key registration and active ZK code are superseded by this note. Historical research documents remain historical records.
