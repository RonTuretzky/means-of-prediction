# Continuous NYT email settlement

Updated 2026-09-10. This is an independent DigitalOcean worker for the **new Sepolia deployment**, using issue.fund's durable collection and restricted-signing design. It runs when the operator's Mac is asleep. It does not manage issue.fund, migrate the old Gnosis contracts, or publish the static frontend.

## What was reused from issue.fund

The reference was the local `RonTuretzky/issue.fund` checkout at `2c0d300d2c08873b0ddc94798b2b2f26cab57c22`, including its automation working tree and the supplied handoff. The review covered its collector, IMAP handling, encrypted store, relay, restricted signer, Unix-socket transport, and DigitalOcean/systemd operations. Its repository, server, mailbox, signer and database were left untouched.

| issue.fund pattern | Means of Prediction implementation |
|---|---|
| Automatic raw GitHub-email collection | Read-only Gmail intake of NYT sender candidates, preserving raw RFC 822 octets |
| Durable mailbox progress | Per-folder UIDVALIDITY and UID cursor, bounded search ranges, retry before advancing on transient failures |
| Authentication before RPC disclosure | RSA-SHA256 DKIM verification of the complete message before encrypted storage and contract preflight |
| Encrypted SQLite claim queue | Encrypted raw mail and transaction payloads; jobs bind chain, factory, market, source, email and immutable rules |
| Separate signing authority | Dedicated Unix user with no network access; Unix-socket signing requests with chain, function, address and gas restrictions |
| Durable relay reservations | Persist intent before signing, signed bytes before broadcast, and nonce ownership across crashes and replacements |
| Managed cloud processes | Separate systemd services, exclusive process locks, restart behavior and verified database backups |

GitHub App authorization, GitHub conversation locking and issue-specific disclosure approval were not carried over: the input here is a fixed newspaper scope and the output is a contract-checked newspaper proof. There is no public email upload or arbitrary transaction-signing endpoint.

## Running deployment

| Setting | Value |
|---|---|
| Worker | DigitalOcean `mop-email-settler`, droplet `599386463`, NYC3 |
| Host | `159.203.92.112`; SSH restricted by provider firewall to the configured operator IP |
| Compute | 1 vCPU / 1 GiB; $6/month base plan, plus enabled provider backups |
| Runtime | Node 24.21.0, pinned minimal runtime lockfile |
| Network | Sepolia, chain 11155111; mainnet rejected by configuration |
| Factory | `0xdbe9c7f2333a0705eefcac15c58d70859b5b1e2f` |
| Body store | `0xb15d8bf694aab06731d7debb17adac22b10ac3b1` |
| Dedicated relay | `0x3001a11B33A3B9D6eF0c8fd87FA910B5EF18149A` |
| Cadence | Every 60 seconds; 5-second loops during catch-up or pending transactions; RPC/IMAP work adds latency |
| Confirmations | Two blocks after the inclusion block |
| Health endpoint | `http://127.0.0.1:4321/health`, accessible through SSH only |

The production signing-domain scope is exactly `nytimes.com`, `e.nytimes.com`, `e.newyorktimes.com`, and `service.newyorktimes.com`. From mailboxes must belong to `nytimes.com` or `newyorktimes.com`, including their proper subdomains. The existing personal Gmail configuration was copied privately into the worker; it is never placed in a release artifact, provider user-data, repository, frontend, or Actions secret.

Gmail All Mail, Spam and Trash are searched without a date cutoff. Sent messages and drafts are excluded. The worker fetches raw bodies only for NYT sender candidates and independently enforces the authenticated signing-domain scope. A scoped IMAP search can discover a forged From candidate, but it cannot make that message pass DKIM. Missing Gmail folders or transient authentication/DNS/storage errors leave intake unhealthy and retryable. Permanently deleted messages and missing historical DNS keys remain unavailable.

## What settles automatically

The worker discovers every market created by the pinned factory, reading rules at a confirmed block. It checks a received message against the source's signing domain, From regex, signed date window, and effective content regex. Subject, Body and SubjectOrBody modes use the same proof builder as the app. The onchain `checkProof` result is authoritative; JavaScript matching is only a candidate filter.

An accepted proof is submitted directly when its encoded size fits the relay allowance. Otherwise the worker uploads immutable 24,000-byte body pages, reuses existing page hashes, then submits the compact proof with ordered pointers. A restart resumes the durable action and nonce journal. Each transaction is simulated/estimated before a new nonce is reserved and confirmed before the next action proceeds.

This submits YES evidence. It **does not call `resolveNo`**: an empty or incomplete mailbox is not proof that an event did not happen. Existing contracts still permit their ordinary deadline-based manual NO path. Source thresholds are enforced by the market, so one source submission need not resolve a multi-source market immediately. Winning-token redemption and protocol-fee withdrawal remain wallet actions, not relay permissions.

The current fresh factory has no LLM judge. This worker does not request new GasKiller judgments. Its body semantics are the single-part, source-byte substring profile in [BODY-PARSING.md](BODY-PARSING.md), not arbitrary natural-language interpretation of Polymarket rules. It cannot settle a Polymarket contract or infer a NO result from an affirmative email.

## Signing, privacy and failure limits

- `mop-settler` can read its Gmail credential, encrypted database and decryption key. It cannot read the relay private key. `mop-signer` can read its own key and reservation ledger, but cannot read Gmail credentials. Systemd gives the signer a private network namespace and permits only Unix sockets.
- The signer allows only zero-value `submitProof`, `storeChunk` and `submitWithChunks` transactions on the configured chain. Market addresses are derived from the pinned factory's actual two-clones-per-market creation sequence and cross-checked during indexing. Trading, approvals, withdrawals, key registration, cancellation transactions and NO resolution are rejected.
- Limits: 16,000,000 gas per transaction, 2 gwei maximum gas price, and **0.10 Sepolia ETH per UTC day in worst-case gas reservations**. Reservations are conservative and are not released when actual gas usage is lower. There is no automatic gas-wallet top-up. The operator must replenish test gas when required.
- The daily cap was exercised during testing: the original 0.02 test-ETH allowance paused a large upload; increasing it resumed the saved nonce. A compromised collector could still request allowed but useless body uploads and consume the bounded gas allowance. The signer is not an independent DKIM verifier for each page.
- Raw messages and signed transaction payloads use AES-256-GCM with per-record associated data; SQLite uses WAL and FULL synchronization. Public market metadata and operational counters are not encrypted. Decryption keys are protected separately on disk but available to the running service and root/cloud operator; this is not protection from a compromised host.
- Authentication happens before proof-bearing RPC calls. Once a candidate is checked, its proof goes to the configured RPC provider. Accepted Body proofs and page uploads publish the **entire canonical body**, plus the signed headers and signature. Subject-only proofs publish signed headers/signature. This flow provides authenticity, not confidentiality.
- Intake rejects messages over 512 KiB. Contract bodies remain limited to 192 KiB, the witness to 4 KiB, and the documented MIME/regex profile. Pagination does not make final verification cheaper or support larger bodies. See [size issue #1](https://github.com/RonTuretzky/means-of-prediction/issues/1) and [GasKiller proposal #2](https://github.com/RonTuretzky/means-of-prediction/issues/2).
- The encrypted payload store stops accepting work at its 256 MiB capacity guard. It does not automatically prune the email archive or nonce journal. Storage maintenance and retention policy are backlog work.
- Missing registry keys, unaccepted proofs, budget exhaustion, insufficient balance, reverts and unknown nonce consumption are visible as waiting/attention states or unhealthy service codes. The worker cannot authorize a new newspaper key; the registrar must authenticate and register it separately.
- An uncertain response retries the same signed bytes. A transaction unconfirmed for two minutes can be repriced only with the same nonce and payload. Recent confirmed receipts are checked for reorganizations within 128 blocks, bounded to the latest 64 confirmed actions. Deep reorg recovery remains an operator procedure.
- Health and systemd logs expose only operational codes and counts. External alert delivery is not configured. The health endpoint must be monitored to surface problems without opening the server manually.

## Verified cloud result — September 10, 2026

The worker is healthy in automatic mode, with the NYT-only domain policy restored, **132 authenticated NYT messages** retained, and both mailbox and market indexing caught up. The database also retains the one explicitly synthetic test fixture. Both test jobs and all ten relay actions are confirmed; there are no pending relay transactions. The dedicated wallet had approximately 0.0995 Sepolia ETH remaining at verification. There are currently no unresolved eligible NYT markets in this fresh factory; this result demonstrates the automation, not a real newspaper-triggered production payout.

| Public synthetic case | Settlement | Winning redemption | Protocol fee |
|---|---|---|---|
| Subject | [Receipt](https://eth-sepolia.blockscout.com/tx/0xe311b04636a6e39b88a68073cd515d738931e8d8ad76164ea4daadf94d660e99) | [Receipt](https://eth-sepolia.blockscout.com/tx/0xbcdfdc8574da2fa060daabb46393069c73fb96ec81c4b9c8448c4fb74d9699bc) | [1 test USDC](https://eth-sepolia.blockscout.com/tx/0xc2238feb901a2f7ef69c48f3c485132624d22f126caf003b910e66584f08c403) |
| Body, 168,786 bytes / 8 pages | [Receipt](https://eth-sepolia.blockscout.com/tx/0xd63513a63acdc502d94afd1e3ceb253ab103d51aeb865383ae89256284fbb117) | [Receipt](https://eth-sepolia.blockscout.com/tx/0x519cc5c07339964c732f94992bb91055ee325f5529fd87d493619dc5f5369d34) | [1 test USDC](https://eth-sepolia.blockscout.com/tx/0x9a18bb97a06b117b1db626faace181a1523b978bb67e47571d3b4bc1b70b6e6b) |

The body-page uploads used **37,575,165 gas**; final body settlement used **5,031,581 gas**. Including subject settlement, the ten relay transactions used **45,968,187 gas** and 0.06204558 Sepolia ETH at the observed prices. These figures exclude creation, funding, trading, redemption and fee withdrawal. Winning redemption paid 185.422971 test USDC per case. Each 100-test-USDC buy generated the verified 1-test-USDC protocol fee.

The deployed services were restarted during the upload and after completion. A budget pause resumed the same reserved nonce, and a fee increase produced a replacement transaction with the same nonce/payload. A duplicate fixture injection remained one stored message and two jobs. All ten mined transactions were independently read back from Sepolia: sender, destination, nonce, zero value, gas bounds, reconstructed serialized hash and relay-size bound matched. The largest serialized envelope was 24,177 bytes.

[Machine-readable public receipts and checks](automation-sepolia-test.json) contain no real email content. The final code snapshot is `e7e0116efc84f81ac1d4d5e6a7c3d7be8b0192a6237385865a281ac6cc04116b`. Reciprocal credential isolation, exclusive process locks, backup timers and off-host encrypted restore checks all passed after restoring newspaper-only operation.

## Operator commands and recovery

Run these from the repository root with Node 24.21.0 or later:

```sh
# First-time setup only; preserves existing private keys/configuration.
node ops/settler/prepare-config.mjs
node ops/settler/provision.mjs
# Wait for bootstrap, rerun provision to record the public IP, and enroll
# the new host in the private known_hosts file before the first deployment.
node ops/settler/deploy.mjs --configure

# Code-only deployments preserve the remote service configuration.
node ops/settler/deploy.mjs

# Private health, optional controlled restart, and backup/isolation verification.
node ops/settler/inspect.mjs
node ops/settler/inspect.mjs --restart
node ops/settler/inspect.mjs --verify
```

Private operator files live in `~/.config/means-of-prediction/worker/`, including the provider credential, pinned SSH host key, service configs and separate storage keys. Configuration defaults to dry-run on a new setup. Set `collector/config.json`'s `enabled` flag only after verifying the chain, allowed domains, funded relay and intake; deploy with `--configure` to apply it. Existing configured deployments are preserved by the setup script. To pause, set `enabled: false` and deploy configuration, or stop the collector service. This prevents further signing/rebroadcasting; transactions already accepted by the chain can still execute.

Runtime snapshots include only explicit automation modules, four shared parser files, the mailbox connector, lockfile and systemd files. They exclude test fixtures, the deployer wallet, test runners, private mail, frontend assets and unrelated dirty worktree changes. Each release has a SHA-256 content manifest under `/opt/mop/releases/<hash>/release.json`; `/opt/mop/current` selects it. Configuration is under `/etc/mop/{collector,signer}` and state under `/var/lib/mop-{settler,signer}`. The filesystem protects both service directories with owner-only access.

Daily backup timers run around 04:20 UTC, using SQLite's online backup API and checking the encryption key and database integrity. Provider backups are also enabled. `inspect.mjs --verify` downloads encrypted, consistent snapshots to the operator's private `~/.local/share/means-of-prediction/worker-backups/` and verifies that they reopen with the local keys.

For recovery, stop both services and keep them stopped while restoring each database **with its corresponding encryption key and the same dedicated relay key**. Never run a second signer or reuse this wallet in a manual transaction sender. Preserve the nonce journal, reconcile every reserved nonce against the chain and mempool, and hold for operator review if a nonce was consumed by an unknown transaction. A stale backup alone cannot prove that a later transaction was never signed or broadcast. Bring up the signer first, then the collector, and inspect health and pending actions before normal operation. Keep at least one current off-host backup and the private configuration backups accessible.

## Validation

- Fifteen automation tests cover real RSA/DKIM authentication, body tampering, scope checks, encrypted storage, dry-run relay suppression, sparse UID ranges, UIDVALIDITY changes, transient failures, size/sent/draft exclusions, signer restrictions and budgets, uncertain signing/broadcast responses, replacement retries, reorg replay and backup restoration. Ten existing research/mailbox tests also pass.
- Local integration uses real deployed contracts, a raw synthetic DKIM email, the IMAP worker interface, Unix-socket signer and durable relay. Both Subject and 168,786-byte paginated Body markets resolved, winning positions redeemed and the 1% platform fee was collected. Coordinator restart preserved progress.
- The cloud integration uses two clearly labelled `body-fixture.invalid` markets and the dedicated relay. The fixture is authenticated through an operator-only test intake; it is **not a live email delivery test**. Actual Gmail authentication and complete NYT catch-up are checked separately. No NYT raw body was published by this integration test.
- Runtime isolation checks verify reciprocal credential denial, exclusive process locks, Unix-only signer networking, rejection of an invalid signing request, loopback-only health, active backup timers and restored databases. The runtime dependency audit reports zero known vulnerabilities at deployment time.

To reproduce the public synthetic integration test (it spends Sepolia test ETH and publishes the fixture):

```sh
node --experimental-strip-types app/automation/e2e.mjs --sepolia
node ops/settler/test-deployed.mjs --inject
# Wait for both markets to resolve; inspect.mjs reports confirmed transactions.
node --experimental-strip-types app/automation/e2e.mjs --sepolia --finish --wait
node ops/settler/test-deployed.mjs --restore
node ops/settler/inspect.mjs --verify
```

The test temporarily adds only the explicit synthetic domain to the two service policies; restore removes it. The signer remains single-instance throughout and keeps the same nonce ledger. Test reports and full diagnostics stay in private operator storage; public transaction receipts can be shared without copying any real email.

The local daily Polymarket/NYT coverage research automation is separate and unchanged. The former Actions settlement workflow is now a manual dry-run diagnostic in this worktree; it will change remotely only with the coordinated repository release. No commits, pushes or Pages publication accompany this deployment.
