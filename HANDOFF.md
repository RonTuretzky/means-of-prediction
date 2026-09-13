> **Update 2026-09-13 (parallel research):** Regex round four is complete at a documented practical plateau; Astra-prose/local-Qwen3.5-35B-A3B optimization continues independently. The regex round used 161 factual candidates, 1,520 synthetic controls, 91 weak natural pairs and 143 archived emails. None of five prompt revisions qualified to replace its baseline. All 48 fresh evaluation generations completed and were frozen before fixture import; host and private v9 native results agree, with no positive checks recognized. Keep these new test labels out of Qwen training. A provenance audit corrected the original teacher input description: 142 texts were cleaned upstream; 32 additional audited batches supplied every full body before the fifth revision. Earlier artifacts remain unchanged. The unapplied v9 RegexLib fork reaches 61/63 baseline lexical witnesses within 16M matcher gas, without establishing settlement semantics. See the research docs and private `REPORT.md`, `PROGRESS.json` and audits. No live prompt replacement, commit, push or publication; the release hold remains.

> **Earlier 2026-09-12 result (round one):** Completed Astra prompt optimization from NYT development emails, the 32-call effort pilot, two blind review passes, and all 178 frozen final generations. The 26-market holdout scored 15/78 factual source hits (19.2%); all were late and none matched within the native 16M-gas budget. Its artifacts remain immutable; subsequent rounds explicitly treat this former test as development. See [docs/BLIND-NYT-PROMPT-RESEARCH.md](docs/BLIND-NYT-PROMPT-RESEARCH.md); private details and prompts are under `~/.local/share/means-of-prediction/slides/astra-blind-20260910/`. `pnpm research:nyt-rule` uses the round-one selected method and has not replaced the browser generator or live settlement policy.

> **Update 2026-09-12 (daily research):** Fresh keyset crawl completed with 423,200 final-winner markets; all-mail import has 19,408 received emails and NYT import has 142. The private NYT factual lower bound is now 156 markets (0.03686%), including 12 newly reviewed August annual-CPI buckets from one late newsletter. Only 14 findings were available by closure; original-rule acceptance remains unproven. The remaining 423,044 markets are not exhaustively classified. See private `~/.local/share/means-of-prediction/daily-summary-20260912.md`. Daily automation stays active; today's CPI evidence did not enter the frozen Astra prompt/test corpus.

> **Update 2026-09-10 (continuous email worker):** An independent DigitalOcean NYT collector and restricted signer are deployed for the new Sepolia factory, following issue.fund’s durable automation architecture. Runtime, encrypted state, private configuration and relay wallet are separate from issue.fund. See [docs/AUTO-SETTLEMENT.md](docs/AUTO-SETTLEMENT.md) for active scope, test receipts, health/backup commands and recovery. The local research automation remains separate. No Gnosis migration, commits, pushes or Pages publication occurred; the shared-worktree release hold still applies.

> **Update 2026-09-10 (body parsing/pagination):** Fresh Sepolia contracts and immutable body-page store are deployed; runtime bytecode and full public synthetic lifecycles passed. `contracts/deployments/sepolia.json` now points to these verified deployments, superseding the stale-address warning below for that file. The LLM judge is disabled on this fresh deployment; existing LLM work is preserved. See [docs/BODY-PARSING.md](docs/BODY-PARSING.md), [size/cost issue #1](https://github.com/RonTuretzky/means-of-prediction/issues/1), and [GasKiller issue #2](https://github.com/RonTuretzky/means-of-prediction/issues/2). No Gnosis migration, commits, pushes or Pages publish occurred. Shared-worktree coordination still applies.

> **Update 2026-09-09:** See [docs/REFACTOR-STATUS.md](docs/REFACTOR-STATUS.md) for the DKIM-only refactor, registrar trust model, platform fees, daily email research, tests and remaining activation steps. The note below is the preserved earlier handoff.

> **Checkpoint 2026-09-13:** The user explicitly requested a local commit of the accumulated code and research process before continuing. Read [QWEN-RESUME-HANDOFF.md](docs/QWEN-RESUME-HANDOFF.md) first for current state, model-switch instructions, private artifact locations, and exact resume gates. This authorizes the checkpoint commit; it does not authorize publishing or deployment. Historical statements that nothing is committed or that commits must wait are superseded for this checkpoint. Earlier deployment/status sections remain historical rather than current health claims.

# Means of Prediction — historical handoff

_Last updated 2026-09-09. Worktree: `~/conductor/workspaces/research/porto-novo`, branch
`RonTuretzky/zkemail-regex-prediction-market`. Repo: `RonTuretzky/means-of-prediction` (remote `mop`, **public**)._

Prediction markets settled by DKIM-signed newspaper breaking-news alert emails. Anyone can open a
market over any set of newspapers and a headline condition; anyone can settle one by submitting a
signed alert email, whose RSA signature is verified **onchain**.

---

## 1. Read this first: the tree is shared and nothing is committed

**Two Claude sessions have been working in this one worktree.** `main`/HEAD is at `a2ec6320e`
(2026-08-25) and everything since then is uncommitted. Do not `git clean -fd`, `git restore`, or
`git stash` here without reading this section.

| Whose | What | State |
|---|---|---|
| Session A (this one) | DKIM soundness fixes, `HeaderParser.sol`, exploit tests, app fixes | untracked + modified, **all tests green** |
| Session B | LLM-judge / Gas Killer track (`contracts/src/judge/`, `LLMJudge.t.sol`, `Qwen35Pins.sol`, `app/scripts/judge/`) | untracked, appears complete (its 18 tests pass) |

**Why nothing is committed.** The soundness fix needs the updated `contracts/test/MarketTestBase.sol`
(fixtures must now sign a `date:` header). That file imports `../src/judge/ILLMJudge.sol` from
Session B's **untracked** directory, so:

- committing the fix alone ⇒ `main` no longer builds;
- committing everything ⇒ lands Session B's unfinished work, **including
  `contracts/deployments/sepolia.json` pointing at addresses with no code onchain**. The Pages build
  reads that file, so this would break the live Sepolia site.

The user's decision (2026-09-05) was: **wait for Session B to land, then commit the fix on top.**
That is still the plan and is still blocked.

**Backup:** everything is copied to `~/mop-soundness-backup/` — the new files, `my-edits.patch`
(Session A's five modified files) and `worktree-snapshot.patch` (all uncommitted changes, both
sessions). If the tree is ever clobbered, recover from there.

---

## 2. Live state (all healthy as of 2026-09-09)

| | |
|---|---|
| App | https://ronturetzky.github.io/means-of-prediction/ — 42 markets render on **both** Gnosis and Sepolia, no errors |
| Gnosis (chain 100) | factory `0xEb6dedbf1BCE0B0D60e7f807304AEA680925baA9`, 42 markets, ~0.10 WXDAI total liquidity |
| Sepolia (11155111) | factory `0x534bf057b115Ca133C982f42acDB3Fc8fe8B3b4b` — **the committed one; use this, not the one in the dirty `sepolia.json`** |
| DKIM keys | **561 real newspaper keys** registered on both chains (97 outlets) — see `docs/DKIM-KEYS.md` |
| CI | `Pages` deploys the app; `Settle` runs daily 13:17 UTC and is **green but dormant** (see §5) |

Deployer/settler key: `0x354fA317d43A36e2f18caAfc70aEd5f2FAD3CB86`, file `~/.mop-deployer.json`
(chmod 600) + repo secret `PRIVATE_KEY`. The **original** deployer key was pasted in plaintext and is
**burned** — never reuse it or fund `0x6636A1CCBdf54485067304C1a590DE016DeaD9F0`.

---

## 3. Three soundness bugs — fixed, not yet committed, **still live onchain**

`DKIMVerifier.verify()` failed to bind three fields to the signed bytes. Found 2026-09-05, all three
reproduced with real RSA signatures in `contracts/test/DKIMBindingExploit.t.sol`.

| Bug | Attack | Fix |
|---|---|---|
| `timestamp` never bound to signed `date:` | a genuine 2024 email settles an Aug-2026 window | must **equal** the signed date |
| `subject` bound by substring `contains()` over the whole header | a **correction email settles as the alert it retracts** | must **equal** the signed `subject:` field |
| `bodyExcerpt` never bound at all | arbitrary attacker text resolves a Body/`SubjectOrBody` market YES | non-empty body **refused** |

The attacker only needs one genuinely-signed newsletter from any of the 561 registered domains —
obtainable by subscribing.

**Fix:** new `contracts/src/lib/HeaderParser.sol` (line-anchored field extraction so a name inside
another field's value can't be smuggled in, plus a fail-closed RFC-2822 date parser; 48 tests) wired
into `DKIMVerifier`. Invariant now: *every field in a proof is derived from the signed bytes, or
refused.* Cost: `verify` 167k → 299k gas, `submitProof` ~2.49M → 2.61M (~$0.004 on Gnosis).
Full suite **149/149**.

App-side (also uncommitted): prover sends empty `bodyExcerpt`; create wizard defaults to Subject with
Body disabled and explained; settlement bot redacts subjects under CI.

**The 42 live markets cannot be patched** — EIP-1167 clones capture the verifier address at creation.
User has accepted this and wants a **fresh deployment** (§6). Exposure today is ~10¢, all of it in the
one `SubjectOrBody` market ("Fed rate cut announced by October 2026?").

---

## 4. There is no zero-knowledge in this system

Settlement is **real DKIM signature verification onchain** (RSA-SHA256 via the modexp precompile) plus
an onchain regex (`RegexLib.sol`, a 580-line NFA differentially tested against JS RegExp). Both are
genuinely real. **Neither is zero-knowledge.** The email lands in public calldata.

A homegrown zk-regex pipeline exists and **works** — fresh circuit build 27.9s, 150,593 constraints,
76.5 MiB zkey, ~2.6–3.0s warm proving, **190,181 gas** onchain `verifyProof`. But its circuit takes
`fromIn[48]`/`contentIn[160]` as *private prover-supplied strings* and never touches RSA/SHA-256, so
it is **not a settlement path on its own** and gives zero privacy while the DKIM check stays public.
It is wired to nothing and deployed nowhere. Leave it that way.

A full adversarial evaluation of adopting `@zk-email/circuits` is in
**`docs/ZKEMAIL-PRIVATE-SETTLEMENT.md`** (505 lines). All four load-bearing claims were **refuted**;
recommendation is a *separate private product*, not migration. Headline blockers: one circuit **and one
trusted-setup ceremony per market condition** (conflicts with permissionless creation); measured
~2.4–2.7 GB prover RSS for a regex-only circuit; our keccak-keyed registry is incompatible with their
Poseidon commitment; and ZK would not hide the market condition, the nullifier, or the payout anyway.

⚠️ Docs still overclaim: `README.md:5` says "settlement is a zkEmail proof", plus references in
`ARCHITECTURE.md`/`BACKLOG.md` and 4 UI strings. **Onchain market descriptions are clean (0 of 42).**
Correcting the wording to "DKIM proof" is an open task.

---

## 5. The settlement bot is dormant by design

`app/scripts/settlement-bot.mjs` + `.github/workflows/settle.yml` (daily 13:17 UTC). It reads a mailbox
over IMAP, parses each email's real DKIM signature, matches it against every live market, dry-runs
`checkProof`, submits `submitProof`, and calls `resolveNo` past deadline+buffer. Unseen DKIM keys are
fetched from DNS and registered permissionlessly.

It has **never processed an email**: `GMAIL_USER`/`GMAIL_APP_PASSWORD` were never set, so the job takes
a skip path and reports green. Runs were failing red daily until `d58e36421` made "unconfigured" a
skip rather than an error.

**Before enabling it**, note the bot previously wrote subject lines into public CI logs and the JSON
artifact. That is fixed in the working tree (redaction under `GITHUB_ACTIONS`) but **is not committed** —
enabling it against the committed version on a public repo would publish subjects.

It has been verified end-to-end once: on Sepolia it parsed two fixture `.eml`s and settled market #0
YES onchain (txs `0xa7151f0a…`, `0xc0abc005…`, ~2.9M/3.3M gas).

---

## 6. Planned next steps

1. **Session B lands** its judge work → re-run `forge test --ffi` (expect 149/149) → **commit the
   soundness fix on top**. Keep `contracts/deployments/sepolia.json` out unless it has been
   re-broadcast.
2. **Fresh deployment** carrying the fixed verifier, then:
   - re-register the 561 keys: `register-dkim-keys.mjs --registry <new>` (idempotent);
   - recreate the board: `create-markets.mjs docs/polymarket-board.json` — **set every config to
     `contentField: "subject"`**, since Body conditions can no longer settle;
   - decide whether to re-register the committed demo DKIM key on mainnet. Recommendation: **no** —
     keep fixture settlement to Sepolia. (It is currently revoked on Gnosis for all 8 domains.)
3. Fix the zkEmail wording (§4).
4. Optional: enable the settlement bot (§5) once its redaction fix is committed.

---

## 7. Gotchas that will bite you

- **Public RPCs and `eth_getLogs`.** Log scans start at `deployBlock` and the window grows daily
  (Gnosis is now ~325k blocks). `gnosis-rpc.publicnode.com` 403s batched scans and caps ranges at 50k on
  some pool nodes and **10k on others**; on Sepolia it returns an **empty set instead of an error**.
  `app/src/lib/wallet.tsx` splits every `eth_getLogs` into **9k windows** and falls back across
  providers (`rpc.gnosischain.com` first). Any new log-scanning code inherits this automatically —
  don't bypass `publicClient`.
- **Gnosis block gas limit is 17M and market creation compiles the regex to a DFA onchain.** Maximal
  patterns cost ~15.4M gas; the compact rewrites are ~4M. Keep new market regexes tight.
- **`rpc.gnosischain.com`'s load balancer is inconsistent** — it produced phantom reverts and nonce
  desync during batch market creation. `create-markets.mjs` takes `RPC_OVERRIDE`; publicnode was more
  reliable for writes.
- **Newspaper preset DKIM domains are inferred** from live DNS keys, not confirmed from received mail.
  90 of the 99 presets are marked `verified: false` for that reason — confirm a `d=` from one real
  email before relying on any of them.
- Commits on this repo carry **no Co-Authored-By tag** (user preference).

---

## 8. Map

```
contracts/src/zkemail/    DKIMVerifier (RSA + field binding), DKIMRegistry (561 keys), RSAVerify
contracts/src/lib/        RegexLib (onchain NFA), HeaderParser (NEW, uncommitted)
contracts/src/market/     HeadlineMarket (the oracle), MarketFactory (EIP-1167 clones), FPMM
contracts/src/judge/      Session B's LLM-judge track (UNTRACKED)
app/src/lib/              prover.ts (.eml -> EmailProof), dkim.ts (canonicalization), wallet.tsx (RPC)
app/scripts/              settlement-bot, create-markets, register-dkim-keys, discover-dkim, zkregex/
docs/                     ZKEMAIL-PRIVATE-SETTLEMENT.md, DKIM-KEYS.md, NEWSPAPERS.md, BACKLOG.md,
                          USER-FLOWS.md, ARCHITECTURE.md, polymarket-board.json
```

Tests: `cd contracts && forge test --ffi` (149) · `cd app && pnpm e2e` (9 Playwright, isolated anvil).
