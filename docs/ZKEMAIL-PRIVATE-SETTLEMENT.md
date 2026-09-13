# zkEmail and a private settlement path — evaluation

Status: research memo, decision-grade. Written 2026-09-05.
Scope: should Means of Prediction adopt `@zk-email/circuits` (or any ZK path) so that the
settlement email never appears in calldata?

This document exists because the project has previously used the word "zkEmail" while shipping
**no zero-knowledge at all**. Everything below is written to avoid repeating that. Claims are
marked as measured, cited, or unverified.

---

## 1. Bottom line

Do **not** migrate the newspaper markets to ZK, and do not present any circuit swap as delivering
privacy for the parametric-insurance use case. For newspaper markets the settlement condition, the
source domain, the market question and the payout are all public **by product requirement** — a ZK
proof would hide a headline that is broadcast to millions and archived on milled.com, while
destroying the public evidence trail that is the product's actual differentiator. For the insurance
use case, ZK is necessary but nowhere near sufficient: at least four decisive leaks (public market
condition, plaintext-domain registry lookup, deterministic email-fingerprint nullifier, and a
one-person anonymity set on the payout) survive any circuit you can build, and the shipped
Circom/Groth16 zk-regex stack additionally conflicts head-on with permissionless market creation
(one circuit **and one trusted setup** per pattern).

The honest recommendation is **(b)**: keep the public path for news markets, retire/relabel the
half-built zk-regex track, fix three live soundness bugs and one live plaintext leak that exist
*today*, and treat private parametric insurance as a **separate product** on Noir/UltraHonk — gated
on one measurement nobody has taken yet (bb.js peak RAM and prove time for the real circuit shape on
a 3–4 GB Android).

Two things must be fixed this week regardless of which option is chosen:
`proof.timestamp` is never bound to the signed header (the acceptance window is attacker-chosen),
and `app/scripts/settlement-bot.mjs` prints matched `From`/`Subject`/`d=` to a **public** GitHub
Actions log on a daily cron.

---

## 2. What `@zk-email/circuits` actually is today

### 2.1 Release state

| Fact | Value |
|---|---|
| Latest **stable** `@zk-email/circuits` | **6.3.4**, published 2025-07-09 |
| Only newer publishes | `6.4.0-alpha.0` (2025-07-17), `6.4.1-alpha.0` (2025-07-25) — dormant since |
| Last substantive commit to `packages/circuits` | 2025-02-10 (version bump to 6.3.3) |
| Active 2026 engineering | Noir/UltraHonk (`zkemail.nr` v2.0.0), SDK `3.0.0-nightly.*`, PoPETs-2026 NFA work |
| `@zk-email/contracts` v6.3.2 | Ships **no verifier** — only DKIM registries, the draft ERC-7969 interface, packing/string utils |

The circom track is effectively frozen. Building on it means building on a dependency whose
maintainers have moved on. The 6.4.x alpha line is *measurably slower* than 6.3.4 for the body path.

### 2.2 What `EmailVerifier` proves

Template params: `(maxHeadersLength, maxBodyLength, n, k, ignoreBodyHashCheck, enableHeaderMasking,
enableBodyMasking, removeSoftLineBreaks)`.

It proves:

- RSA-2048 PKCS#1 v1.5 over SHA-256 of the canonicalized signed headers (`assert(n*k > 2048)` — **RSA-1024 is not supported** by the circom EmailVerifier as parameterized; the Noir lib does have `KEY_LIMBS_1024`, but limb count is a compile-time generic).
- Optionally (when `ignoreBodyHashCheck != 1`): that the base64 `bh=` in the header equals SHA-256 of the body, with partial-SHA precompute.

It does **not** prove: the `d=` domain, the From address, the Subject, or the Date. All of those
require *separate, code-generated regex circuits*. Public outputs are exactly three:
`pubkeyHash`, `shaHi`, `shaLo`. **There is no nullifier** (the optional helper computes
`poseidon(signature)` — no user secret, so it is as linkable as our current
`keccak256(signature)`).

`pubkeyHash` is `PoseidonLarge(121,17)(pubkey)` — Poseidon over 9×242-bit chunks — **not**
`keccak256(modulus)`. Our `DKIMRegistry` is keyed on `keccak256(modulus)`, so the 561 registered
keys are incompatible at face value (see §4).

### 2.3 Measured constraint counts and artifact sizes

Measured with circom 2.2.2 `--O2` against `@zk-email/circuits` 6.3.4 + `zk-regex-circom` 2.3.2:

| Configuration | R1CS constraints |
|---|---|
| Header-only (`ignoreBodyHashCheck=1`), maxHeaders=640 | 509,751 |
| Header-only, maxHeaders=1024 | 704,007 (a second measurement of the same shape gave 742,350 — treat ~0.7–0.75M as the range) |
| Header-only, maxHeaders=2048 | 1,224,073 |
| Full body check (640/768) | 1,263,698 |
| Full body check (1024/1536) | 2,067,140 |
| `SubjectAllRegex(1024)` standalone | 370,993 (~362/byte) |
| `FromAddrRegex(1024)` standalone | 966,927 (~944/byte) |
| **Our** regex-only circuit (`circuits/build/000fd839`), no RSA, no SHA | **150,593** |

Artifact sizes, measured: **532.9–542.2 bytes of zkey per constraint**. Concretely:

| Artifact | Size |
|---|---|
| `circuits/build/000fd839/pattern_final.zkey` (our toy circuit) | **80,245,457 B (80.2 MB)** |
| `circuits/pot18_final.ptau` | 302 MB |
| zkEmail's live Proof-of-Twitter zkey (production) | **786.6 MB gzipped / 1.399 GB uncompressed** |
| Projected: header-only 1024 + one subject regex (~0.9–1.07M constraints) | **~400–480 MB per market** |

Proving resources, measured on an M4 Max / 128 GB:

| Measurement | Value |
|---|---|
| `snarkjs groth16 prove` on our 150,593-constraint toy circuit | 2.14 s wall, **peak RSS 2.41 GB** |
| Same, with `--max-old-space-size=512` | peak RSS **2.67 GB** (heap flags do not bound it — off-heap typed arrays) |
| zkEmail's own figure at 3.53M constraints | **~29 GB peak RSS**, ≥32 GB RAM recommended |
| circom *compiling* header-only EmailVerifier | 4.54 GB peak RSS |
| circom *compiling* header+body EmailVerifier | 13.7 GB peak RSS |

zkmopro documents iPhone 15 Pro and Pixel 6 Pro **crashing** on a ~5 GB circuit because phones cap
app memory near 3 GB. Our *toy* circuit already sits at 2.4–2.7 GB.

### 2.4 The Noir/UltraHonk alternative (materially better)

| | Circom/Groth16 | Noir/UltraHonk |
|---|---|---|
| Trusted setup | **Required, per circuit** | Not required (universal Aztec Ignition SRS) |
| Per-market artifact | 400 MB–1.4 GB zkey | ~0.93 MB bytecode + one shared **8.39 MB** SRS |
| Compile time | 8–68 s | 1.7–5.4 s |
| Prove time (1024/1024) | 14.1 s (1,308,426 R1CS) | 2.9 s (237,880 gates) |
| Prove on a 2021 Pixel 6 (zkemail.nr header circuit) | crashes / not viable | **4,757 ms** |
| Prove in browser | minutes | 6,590 ms |
| On-chain verify gas | 318,559 (constant) | 1.885M–1.945M |
| Proof size | 805 B | 14,080 B |
| Regex cost scaling | O(match_len × total_transitions) | O(match_len × constant lookup) |

Caveat, and it matters: **every published Noir benchmark above is a header circuit with no market
regex attached.** The per-market pattern is exactly the unmeasured part. Neither `nargo` nor `bb`
is installed on this machine, so nothing in the Noir column was reproduced locally.

### 2.5 Do not outsource circuit generation to registry.zk.email

zkEmail's hosted Registry is the obvious answer to "compile a circuit per market". It is unusable:

- `zkemail/sdk-images` `generate_keys()` runs `snarkjs groth16 setup` then
  `snarkjs zkey beacon ... 0102030405...1f 10`. There is **no `zkey contribute` anywhere in the
  repo** — zero secret contributions.
- Two independent agents recomputed δ = `10058461782792383316007738437985165872338398992832266730124483776261966611453`
  from that public beacon string, confirmed δ·G2 == `vk_delta_2` against **live production
  verification keys** (including blueprint `5ef75d3c-…`, the one in zkEmail's own quickstart), and
  produced **forged proofs with attacker-chosen public signals, no email and no witness**, which
  `snarkjs groth16 verify` returns `OK!` on. The deployed Solidity verifiers are exported from the
  same zkeys.
- Separately: the SDK defaults to `isLocal: false`, so the server receives the email; SP1 blueprints
  POST the literal raw `.eml`; zkEmail's hosted `noirProver` takes a Gmail OAuth token and fetches
  the user's mail itself.

**This is an unreported vulnerability in a third party's production system. Do not publish, demo, or
cite it publicly before contacting security@zk.email.**

Our own `app/scripts/zkregex/build-circuit.mjs` has the identical defect class — it contributes with
literal committed entropy (`-e=headlines dev entropy`, `-e=headlines zkey entropy`) in a **public**
repo, so every circuit it can build is forgeable by anyone who clones us.

---

## 3. What a private settlement path would concretely require on our side

### 3.1 Contract-by-contract

| Contract | Change |
|---|---|
| `contracts/src/tokens/ConditionalTokens.sol` | Unchanged |
| `contracts/src/market/FPMM.sol` | Unchanged |
| `contracts/src/utils/Clones.sol` | Unchanged |
| `contracts/src/zkemail/DKIMRegistry.sol` | Add a Merkle root over registered `(domain, modulus)` pairs so the circuit can prove set membership without publishing `d=`; add a circuit-native (Poseidon) key-hash index alongside the keccak one |
| `contracts/src/zkemail/DKIMVerifier.sol` | **Replaced** by a SNARK-backed verifier. `IZKEmailVerifier.verify` is already `view`, so the interface shape survives |
| `contracts/src/lib/RegexLib.sol` | `matches()` becomes dead at settle time; `validate()` still needed by `HeadlineMarket.initialize` |
| `contracts/src/market/MarketFactory.sol` | New implementation address; `CreateMarketParams` gains per-source pattern commitments |
| `contracts/src/market/HeadlineMarket.sol` | New parallel `submitZkProof` / `checkZkProof`; `Evidence` loses `subject` and `emailTimestamp`; `ProofAccepted` loses `subject` and `emailTimestamp` |
| `contracts/src/judge/LLMJudge.sol` | **Excluded outright** — cannot be made private (see §5) |
| `contracts/src/zkemail/ZkRegexVerifierRegistry.sol` | Delete or clearly relabel — it has a live front-running hole (see §4.2) |

### 3.2 Proposed proof struct and submit path

Current (everything is plaintext calldata):

```solidity
struct EmailProof {
    string domainName; bytes32 publicKeyHash; uint256 timestamp;
    string fromAddress; string subject; string bodyExcerpt;
    bytes32 emailNullifier; bytes header; bytes signature;
}
```

Proposed:

```solidity
struct ZkEmailProof {
    bytes32 registryRoot;     // Merkle root of registered (domain, modulus) pairs
    bytes32 emailNullifier;   // Poseidon(signature_limbs, proverSecret) — hiding, NOT keccak(sig)
    bytes32 patternCommit;    // commitment to (fromRegex, contentRegex) for this source
    uint256[2] pA; uint256[2][2] pB; uint256[2] pC;
}
// public signals: [registryRoot, nullifier, patternCommit, windowStart, deadline, sourceDomainCommit]
```

Key points:
- The Date/window comparison happens **in-circuit** so no timestamp is ever published.
- The domain is **committed**, not named — which requires the `DKIMRegistry` Merkle redesign.
- The per-source domain check and per-source `fromRegex` check both move inside the circuit, which
  means **circuits are per-source, not per-market** — a 3-of-5 market with five distinct sources
  needs up to five circuits.
- K-of-N logic itself is unchanged: `sourceIndex`, `sourceMatched`, `matchedCount`, `threshold` need
  no edits.

A working reference for the parallel-path shape already exists in git history: `CompiledEmailProof`
and `submitCompiledProof` at `2bb090c3d^`, deleted only because the verifier behind it was a mock.

`HeadlineMarket` has **4,772 bytes of EIP-170 headroom** (runtime 19,804 / limit 24,576), already
compiled with `via_ir = true` and optimizer 200. A parallel path must be surgical or split out.

**Existing markets cannot migrate.** They are EIP-1167 minimal clones with no admin and no upgrade
function (`MarketFactory.sol:81-84`). The live Gnosis factory `0xEb6d…baA9` and every market under
it stay plaintext-only, permanently. The 561 registered DKIM keys do carry over — `DKIMRegistry` is
standalone.

### 3.3 Exhaustive list of places we leak the email today

**A ZK proof that leaves any of these in place is pointless.** All verified in the working tree.

| # | Leak | Location |
|---|---|---|
| 1 | `Evidence.subject` stored in contract storage forever; served by public `getEvidence()` | `HeadlineMarket.sol:52-58`, `:224-232`, `:295` |
| 2 | `ProofAccepted(sourceIndex, submitter, string subject, uint256 emailTimestamp)` emitted | `HeadlineMarket.sol:60-62`, `:233` |
| 3 | Full canonicalized signed header block in calldata — **includes `to:`** on our fixtures (`h=from:subject:date:to`), i.e. a real recipient address | `IZKEmail.sol:21-22` |
| 4 | `fromAddress`, `subject`, and a ≤4096-byte `bodyExcerpt` as separate plaintext calldata fields | `IZKEmail.sol:18-20`, `dkim.ts:23` |
| 5 | `domainName` must stay public because the registry is a plain mapping read on the plaintext domain string — **survives any circuit as currently architected** | `DKIMVerifier.sol:37`, `DKIMRegistry.sol:33-39` |
| 6 | The market's own condition — `question`, `description`, `contentRegex`, `criteria`, every `Source.dkimDomain` and `fromRegex` — is public storage, emitted in `MarketCreated`. **No proof system fixes this** | `HeadlineMarket.sol:66-70`, `:99`, `:291`; `MarketFactory.sol:43-51` |
| 7 | Nullifier is `keccak256(RSA signature)` — publicly recomputable by anyone holding the `.eml` | `DKIMVerifier.sol:46` |
| 8 | Judged mode: tokenized prompt (containing the subject) in public calldata; `JudgeVerdict` re-emits the full text as `bytes userText`; verdicts keyed by `keccak256(text)` = brute-forceable oracle | `LLMJudge.sol:146-172`, `:74-81`, `:314-316` |
| 9 | `promptKeyFor` is an external view that **returns the Subject** decoded from the header | `HeadlineMarket.sol:328-332` |
| 10 | `checkProof` dry-run ships the entire plaintext email to a third-party RPC via `eth_call`, before the user decides to submit and even when the proof is rejected | `ResolutionPanel.tsx:93-98`; `settlement-bot.mjs:465`, `:559`; default RPCs are publicnode.com |
| 11 | Settlement bot prints `d=`, selector, From and Subject to stdout, to `$GITHUB_STEP_SUMMARY`, and into an uploaded `settle-report.json` artifact — on a **daily cron in a public repo** (verified: `RonTuretzky/means-of-prediction` is PUBLIC) | `settlement-bot.mjs:491`, `:530`, `:587-588`; `.github/workflows/settle.yml:70-79` |
| 12 | Frontend renders other people's Evidence subjects and caches them all | `ResolutionPanel.tsx:172`, `:233`; `ResolutionTimeline.tsx:32`; `useMarkets.ts:39`, `:125` |

Additionally, the settlement bot is a **mailbox-exfiltration primitive**: market creators choose
which domains it searches in the operator's mailbox (`settlement-bot.mjs:477`, `:232`, `[Gmail]/All
Mail`) and which subjects it publishes on-chain. A permissionlessly created market with
`contentRegex = "(?i)."` on a domain the operator receives mail from causes the bot to publish that
mail's subject on-chain and in the public run log.

### 3.4 Frontend and bot breakage

`prover.ts:38 buildEmailProof` (sync, plaintext) becomes an async `groth16.fullProve` against a
400+ MB zkey. `dkim.ts:57 parseDkimEmail` survives as the witness builder. Broken:
`ResolutionPanel.tsx` (:36-51, :93-98, :170-174, :232-239, :277-292), `ResolutionTimeline.tsx:27-35`,
`useMarkets.ts:33-40` + the 23-element multicall tuple at :113-160, `CreatePage.tsx` (must drop
`ContentField.Body`/`SubjectOrBody`, currently the default at :71). E2E: `flows.spec.ts:172-180`,
`record.spec.ts:61,68`. Bot: `:38`, `:73-93`, `:465`, `:527`, `:559`, plus it needs the per-pattern
zkey on the CI runner — `settle.yml` has **no cache or download step**, and a `ubuntu-latest` runner
has 14 GB of disk, capping it at roughly 29 markets' worth of zkeys.

---

## 4. Blockers, ranked

### 4.1 Per-pattern circuit + per-pattern trusted setup vs permissionless market creation — FATAL on Groth16

The regex is **not** part of `EmailVerifier`. It is a separately code-generated circuit whose
automaton is emitted as compile-time constants — verified on both backends:

- Circom: unrolled `eq[0][i].in[1] <== 13;` IsEqual/AND ladders per transition.
- Noir: `global TRANSITION_TABLE: SparseArray<66, Field> = SparseArray { keys: [...], ... }` plus
  hardcoded `check_start_state` / `check_accept_state` polynomials. The helper's own docstring says
  the table "SHOULD BE COMPTIME".
- zkEmail's paper: "This transition set forms an immutable ruleset embedded within the
  zero-knowledge circuit." Their founder: "we have to know the structure of the regex prior to
  deriving the zkey."

So: **a new market condition is always a new circuit.** On Groth16 that means a new phase-2 ceremony
per market, which nobody runs, and the automated substitute (a deterministic beacon) is precisely
what makes the key forgeable (§2.5).

This is not a hypothesis about our system — it is the **observed state**: 42 live markets on Gnosis,
each with its own regex; `circuits/manifest.json` contains exactly **one** entry, and
`circuits/build/` contains exactly one build. A 1/42 coverage rate, months in.

Two further multipliers: RSA key size is a compile-time generic (Noir template hardcodes
`KEY_LIMBS_2048`; circom hardcodes n=121,k=17), and **289 of our 564 registered keys (51%) are
1024-bit** with one 4096-bit key that `PoseidonLarge` cannot hash at all (`assert(chunkSize <= 32)`).
Header length is a third axis. And circuits are per-*source*, not per-market (§3.2).

### 4.2 VK↔condition binding — unsolved by any proving system

In a permissionless market the creator supplies the circuit/VK, and **nothing on-chain can check
that the VK encodes the regex the market publicly declares.** Our own code demonstrates the hole:
`ZkRegexVerifierRegistry.register()` is permissionless and write-once, keyed on
`pairHash(fromPatternHash, contentPatternHash)` — both deterministic public functions of the regex
strings. An attacker precomputes the pairHash for any likely pattern and registers an always-true
verifier **first**; write-once then makes it permanent and unfixable. The contract's own NatSpec
concedes the residual assumption is "that the first registrant compiled the honest circuit."

Both fixes reintroduce what we were avoiding: reproducible-compilation + optimistic challenge
(requires byte-reproducible `nargo`+`bb` VK generation — **unverified**, and noir#2036 is a
documented historical non-determinism bug — plus a socially pinned toolchain version, bonds, and a
challenge window that delays payouts, which is bad for insurance); or an attestation/whitelist, i.e.
permissioned.

### 4.3 Proving feasibility for low-resource users — fatal on Groth16, unmeasured on Noir

Measured (§2.3): a circuit that verifies **nothing cryptographic** already needs 2.4–2.7 GB RSS and
an 80 MB zkey. A real market circuit extrapolates to ~10 GB RSS and a ~480 MB zkey **per market**.
Phones cap app memory near 3 GB.

Bandwidth is not the binding constraint — **cost** is. Ookla 2025 medians are fine (Nigeria 44.1
Mbps, Kenya 45.4 Mbps), but A4AI/World Bank put 1 GB at 2.4% of average monthly income in
sub-Saharan Africa, 5% for the poorest 40%, 24.4% in CAR. A 480 MB per-market zkey is ~1.2% of
average monthly income, ~2.4% for the poorest 40%, ~11.7% in CAR — **per market**, and it does not
amortize because the automaton is baked in at compile time.

The fallback destroys the motivation. zkEmail's own FAQ: "If the server is generating the proof, it
has to have the private input." For us specifically it is worse than lateral — bot-side proving
would relocate medical/bank/claim subject lines from on-chain calldata into a **public CI log**
(leak #11). And structurally it is incoherent: for insurance the triggering email lands in the
*claimant's* mailbox, so bot proving requires the claimant to forward their medical notice to us or
grant OAuth mailbox access — exactly the disclosure the redesign exists to eliminate.

Also worth stating plainly: `grep` for `snarkjs|groth16|fullProve` across `app/src` returns only the
type stub `app/src/types/snarkjs.d.ts`. **Nothing in the frontend has ever generated a proof.** There
is no evidence base for "users can" because no user ever has.

### 4.4 Registry incompatibility

`pubkeyHash = PoseidonLarge(121,17)(pubkey)` vs our `keccak256(modulus)`. Options: (a) prove keccak
of the modulus in-circuit — for the real NYT RSA-4096 key that is 512 bytes of keccak, ~150k+
constraints, as expensive as our entire current regex circuit; (b) add a parallel
`poseidonKeyHash => modulus` index, which cannot be verified on-chain and needs a write-once
commitment discipline or an attestation. Neither is free. Computing Poseidon on-chain at
registration time is also not turnkey: circomlib's Solidity generator caps at 8 inputs, the 6-input
contract is 23,641 B against the 24,576 B EIP-170 limit, and measured Poseidon(6) is 134,415 gas —
zkEmail needs Poseidon(9).

Note also that a Poseidon-hash-only registry **cannot be permissionless** — anyone could register
Poseidon of their own key under `nytimes.com`. Our registry is permissionless *only because* it
stores the modulus and does the RSA check on-chain. Every zkEmail registry variant is permissioned
(`onlyOwner`, or a designated ECDSA signer, or a `mainAuthorizer`). The clean escape exists upstream:
zkEmail's newest `EmailAuthVerifier` exposes the 17 RSA pubkey limbs as public signals 34-50, so a
contract can reconstruct the modulus and keccak it (measured: 94,296 gas naive, <20k in assembly).

### 4.5 Gas is not a motive — and the RSA check is not the cost

Measured with `forge test --gas-report`:

| Component | Gas |
|---|---|
| `submitProof` total | min 2,953 / median 2,465,627 / max 2,483,105 |
| `RegexLib.matches` (called up to 3× per submit) | min 137,744 / **avg 867,214** / max 1,435,638 |
| `DKIMVerifier.verify` | min 12,680 / **avg 167,127** / max 225,413 |
| — of which the RSA modexp precompile | 6,402 |
| Calldata (376 B header + 256 B sig + ~650 B body) | ~21,000 |

**82% of the cost is the on-chain regex, not the DKIM verification.** Swapping RSA-in-Solidity for a
SNARK while leaving the regex on-chain would cost *more* gas, not less. And gas does not matter here
anyway: live Gnosis `eth_gasPrice` returned 9 wei; even at a 1.5 gwei floor, 2.49M gas is ~$0.004.
2.49M also sits far under the 17M block limit, and K-of-N settles in separate transactions.

Note the hidden tax in zkEmail's own `Verifier.sol`: re-packing domain and command strings into
field elements measures ~458k gas — *more* than the Groth16 verify it wraps. Any integration must
take pre-packed field elements in calldata.

### 4.6 Live soundness bugs — must be fixed regardless

These are not ZK questions. They are exploitable today.

1. **`proof.timestamp` is never bound to the signed header.** `grep -rn timestamp
   contracts/src/zkemail/` returns only a struct comment. `DKIMVerifier.verify` checks registry key,
   RSA, nullifier, and two `contains()` searches — it never parses or binds the Date header. The
   `[windowStart, deadline]` window is **attacker-chosen**. Confirmed by construction:
   `MarketTestBase.makeProof` builds headers with no `date:` at all, yet all window tests pass. Not
   in `docs/BACKLOG.md`.
2. **Field binding is a naive `contains()` substring scan over the whole header block**, not
   positional extraction. So `fromAddress` may be lifted from the `to:` line and `subject` may be
   any substring including base64 from `bh=`. The WaPo test source's
   `fromRegex = "@email\\.washingtonpost\\.com$"` is satisfied by a substring of a `to:` header.
3. **`bodyExcerpt` is unbound** (no `bh=` check; BACKLOG A4) and `contentMatches` ORs it with the
   subject — and `ContentField.SubjectOrBody` is the **CreatePage default** (`CreatePage.tsx:71`).
   Any DKIM-signed email from the domain plus an arbitrary 4 KB "body" settles such a market.

Moving to a circuit would fix (1) and (2) by construction, since a DFA scan over a fixed extracted
field is positional. But they should be fixed now, not in six months.

---

## 5. Residual leakage even after adopting ZK

What a zk proof does **not** hide:

| # | Leak | Why ZK doesn't fix it |
|---|---|---|
| R1 | **The market condition itself.** `question`, `description`, `contentRegex`, `criteria`, per-source `dkimDomain` and `fromRegex` are public storage, emitted at creation. A per-claimant insurance market publishes the insurer, the trigger, the window and the creator address **before any email exists** | Data-model problem. zkEmail's own model treats the pattern as public by design (the SDK downloads per-blueprint regex graphs from a public endpoint). Hiding it breaks tradeability — nobody can price a market whose settlement condition is secret |
| R2 | **The email fingerprint.** `EmailVerifier` publicly outputs `shaHi`/`shaLo` = SHA-256 of the entire canonicalized signed header block, which on our fixtures covers `to:`. Anyone holding the `.eml` — the sender, the mail provider, a co-recipient, a subpoena — recomputes it in one line | Public output by construction; you must fork the circuit to drop or commit-hide it |
| R3 | **The nullifier.** Ours is `keccak256(signature)`; zkEmail's optional helper is `poseidon(signature)`. Both are deterministic functions of data the sender already has | Must be redesigned as `Poseidon(sig_limbs, proverSecret)` — a change, not a preservation |
| R4 | **The sender.** `pubkeyHash` is public and DKIM keys map to domains via public DNS. Our registry read additionally forces `domainName` to stay a public input | Requires the Merkle-root registry redesign (§4.4) |
| R5 | **The K-of-N structure.** `sourceIndex` is a plain public argument, `indexed` in `ProofAccepted`; `getSources()` is public | "Source #2 (aetna.com) matched at block T" is announced regardless |
| R6 | **The payout.** Claimant buys YES (`Buy(address indexed buyer, ...)`), then redeems (`PayoutRedemption(address indexed redeemer, ...)`). Buy → email → settle → redeem, on a market whose public question describes the claim, with an anonymity set of one | Needs fresh addresses, delayed redemption, and pooled markets — a product change, not a circuit |
| R7 | **Timing.** Even with the timestamp moved in-circuit, the settlement tx timestamp plus the public `windowStart`/`deadline` bound the email's arrival | Inherent |
| R8 | **Judged (LLM) mode is unfixable as designed.** Verdict is computed by the Gas Killer fleet over the plaintext prompt; the tx carries the tokenized prompt as `uint32[]` calldata; `JudgeVerdict` re-emits the full text; verdicts keyed by `keccak256(text)` make it a brute-forceable oracle (question and criteria are public, so the subject is the only unknown). Operator set is n=3, all Gas Killer's own GKE pods, 0.003 total test-stETH staked | Should be **excluded outright** from any private product, not ported |

**Net:** post-adoption, a passive block-explorer scraper learns less. The insurer, the mail provider,
the bot operator, and anyone who reads the market's own question learn essentially everything they
learn today. For a claimant, those are the adversaries that matter.

The one genuine, ZK-only win: real newspaper alerts are bulk mail, and RFC 8058 requires the DKIM
signature to cover `List-Unsubscribe` / `List-Unsubscribe-Post` when present, while `to:`
over-signing is standard anti-replay practice. So a production alert's signed header block plausibly
carries the settler's own email address and a per-recipient unsubscribe token — inside the RSA-signed
bytes, so unredactable without breaking the signature. Today that goes into public Gnosis calldata
forever, and only a circuit fixes it. **Unverified:** every file in `emails/` is a dev re-signature
with `h=from:subject:date:to`, and BACKLOG E4 records that no market has ever been settled with a
real alert — we have never seen a production `h=` list. The harm is inferred, not observed. The
~$0 mitigation is to settle from a dedicated burner subscription address plus the A5 settler bounty
so one relayer settles everything.

---

## 6. Options with honest cost/benefit

### Context that should inform the choice

Verified against Gnosis mainnet (factory `0xEb6d…baA9`): `marketCount() = 42`. Exactly **one** market
has any liquidity (lp = 5e16, the deployer's own seed); 41 have lp = 0. **Zero markets are resolved.
Zero `ProofAccepted` events.** BACKLOG E4: "Remaining: subscribe to the alert lists and settle a
market with a real breaking-news email end to end." Also: `grep -rn "insurance\|parametric\|global
south" docs/ README.md app/src contracts/src` returns nothing substantive — parametric insurance is
not a feature of this product; it is a different product being used to justify rework on this one.

### (a) Do nothing to the settlement path; fix the naming and the live bugs

| | |
|---|---|
| **Effort** | 3–5 days |
| **What** | Retire or clearly relabel `ZkRegexVerifierRegistry` + `app/scripts/zkregex` + `circuits/` (they are a research track wired to nothing, with committed toxic waste and a front-running hole). Fix `docs/ARCHITECTURE.md`, which still documents the deleted `submitCompiledProof` / `ZkEmailVerifierV2`. Stop calling the live path "zkEmail" — it is on-chain DKIM verification, which is a good, honest, auditable thing. Fix the three soundness bugs (§4.6). Strip From/Subject/domain from the bot's stdout, step summary and report artifact |
| **Benefit** | Removes a live public plaintext leak and an attacker-chosen settlement window; stops overclaiming |
| **Cost** | No privacy gained. Settler's subscriber address still goes into calldata |

### (b) Keep the public path for news markets; build a separate private insurance product

| | |
|---|---|
| **Effort** | (a) plus **3–6 months** for a credible private product, and only if the §7 gate passes |
| **What** | News markets stay public — public evidence is the differentiator and the condition must be public to be tradeable. Private parametric insurance is a **new product**, not a migration: new implementation + new factory (clones have no upgrade path anyway), Noir/UltraHonk (never per-market Groth16), Merkle-root `DKIMRegistry`, hiding Poseidon nullifier, forked circuit with `shaHi`/`shaLo` dropped, committed rather than published condition, pooled markets for anonymity-set size, LLM-judge path excluded |
| **Benefit** | The only option that could actually serve the stated use case, and it isolates the risk |
| **Cost / risk** | The four hardest problems (R1, R4, R6, and VK↔condition binding) are **design** problems that no proving system solves. R1 in particular is in direct tension with the market being fundable and priceable — an underwriter must know what they underwrite. Also unresolved: how "permissionless" survives §4.2 |

### (c) Full migration of HeadlineMarket to ZK

| | |
|---|---|
| **Effort** | 4–8 months, and it does not achieve the goal |
| **What** | Rewrite the settlement path, registry, frontend, bot and tests |
| **Benefit** | Removes the settler's subscriber address from calldata (the §5 win) |
| **Cost** | Existing 42 markets **cannot migrate** (EIP-1167, no admin). Only 4,772 B of EIP-170 headroom. Downgrades a publicly-auditable oracle to an opaque one — on the current code, to a *forgeable* one. Makes settlement require a 400–480 MB download and multi-GB RAM, killing the "anyone can settle by pasting an .eml" property that the product's liveness depends on. Saves ~$0.004 per settlement. Hides a headline that milled.com archives publicly |

---

## 7. Recommendation and the smallest de-risking next step

**Recommendation: (b).** Keep the public path for news markets. Do the (a) work now. Treat private
parametric insurance as a separate product, and **do not start building it** until the gate below
passes.

### The gate — one measurement nobody has taken

Compile the **real circuit shape** in Noir and benchmark it:

- 1024-byte canonicalized header, `ignoreBodyHashCheck=1`
- RSA-1024 **and** RSA-2048 variants (51% of our registered keys are 1024-bit)
- **one market regex attached** — this is the part every published benchmark omits
- measure `bb.js` prove time **and peak RSS** on an entry-level 3–4 GB Android, not on an M-series laptop
- measure the generated `HonkVerifier` bytecode size against EIP-170 and its deploy + verify gas on a Gnosis fork

Decision rule: if it lands under **~2 GB peak RSS and ~30 s** on that device, client-side proving is
viable and the architecture is Noir/UltraHonk. If it does not, client-side proving is dead for the
target population, and the honest options are a TEE-attested prover or dropping the privacy claim —
not a better circuit.

Estimated effort for the gate: **1–2 weeks** (install `nargo` + `bb`, port one pattern, borrow a
cheap Android handset). That is the cheapest thing that turns this from an argument into a decision.

### Do this week, independent of the decision

1. Bind `proof.timestamp` to the signed `Date` header (§4.6.1) — live soundness bug, not in BACKLOG.
2. Replace `contains()` binding with positional header-field extraction (§4.6.2).
3. Implement the `bh=` body-hash check, or remove `ContentField.Body`/`SubjectOrBody` — currently the
   CreatePage default and forgeable (§4.6.3).
4. Strip From/Subject/`d=` from `settlement-bot.mjs:491, :530, :588` and drop the `settle-report.json`
   artifact upload — the repo is **verified public** and the workflow runs daily.
5. Delete the committed dev entropy in `build-circuit.mjs` rather than carrying it forward.
6. Settle one market end-to-end with a real alert (BACKLOG E4). That proves the product *and* gives
   us the first real production `h=` list — the only way to actually measure the leak in §5.
7. Contact security@zk.email about the Registry beacon finding before any public write-up.

---

### Confidence notes

- **Measured locally in this repo / on this machine:** constraint counts, zkey sizes, prover RSS, gas
  report, contract sizes, Gnosis market state, repo visibility, all twelve leak locations, all three
  soundness bugs.
- **Reproduced independently by two agents:** the registry.zk.email beacon forgery.
- **Cited, not reproduced:** all Noir/UltraHonk performance figures (`nargo`/`bb` are not installed
  here), the PoPETs-2026 paper numbers, the A4AI affordability figures, zkmopro's mobile crash reports.
- **Unverified and flagged as such:** whether production newspaper DKIM signatures actually over-sign
  per-recipient headers; whether `nargo`+`bb` VK generation is byte-reproducible; the gate benchmark
  in §7; the ~10 GB RSS extrapolation for a full market circuit (extrapolated from two datapoints on
  the same curve, not measured).
