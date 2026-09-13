# Settling without regex: Gas Killer's on-chain LLM as the judge

*2026-08-22. Evaluation of integrating [llm.gaskiller.xyz](https://llm.gaskiller.xyz) —
Gas Killer's "language model running on Ethereum" — so that a market resolves on a
natural-language criterion judged by a model, instead of a regex, while keeping the
DKIM-signed newspaper email as the evidence. Every claim about Gas Killer below was
checked against the `gas-killer/*` sources (solidity-sdk, service, gas-analyzer,
example-contracts, site docs, open PRs) and, where it mattered, against Sepolia state.
Judge quality was measured locally on a 480-headline corpus. Working files:
`.context/gk-*` (brief, corpus, designs, verdicts, eval harness + outputs).*

## 0. Verdict in one screen

**What Gas Killer is.** An EigenLayer AVS for verifiable off-chain EVM execution. A
consumer contract inherits `GasKillerSDK` and marks a function `trackState`; operators
simulate the call off-chain (under an "unbounded" profile, up to 2^40 gas per call),
extract the storage diff, BLS-sign it, and the client submits one `verifyAndUpdate` tx
that applies the diff after a quorum-signature check. The LLM demo is exactly that with
a bit-exact integer Qwen3-0.6B (and a Qwen3.5-35B-A3B) written in Solidity as the
tracked computation, weights pinned by a 32-byte manifest hash.

**What it would give us.** The regex disappears. A market stores `criteria` ("the
United States has begun a military invasion of Iran"); settlement becomes: DKIM-verify
the email on-chain (unchanged, fully cryptographic) → an LLM judges whether the
*signed* Subject establishes the criterion → the market consumes the verdict and
reports payouts. The blast radius of the LLM is small by construction: a verdict can
only ever be about a **real, DKIM-valid, in-window email from a configured newspaper**
— the worst a dishonest judge can do is misread a genuine headline, never invent one.

**Is it "trustless"?** Not today, and the word should not be used yet. Today a verdict is
an *attestation* by ≥66 % of stake of a 3-operator quorum — three Kubernetes pods run by
Gas Killer themselves, 0.001 Sepolia test-stETH each, one admin EOA. There is **no
fraud proof, no bisection game, no slashing deployed** (the "Bisection Proof Lab" on
the demo page is a browser simulation; the slasher lives in open PRs sdk #46→#66 /
service #345). What *is* true, and is the reason this is worth doing, is that the
judgement is **objectively re-executable**: deterministic integer inference, greedy
argmax, pinned weights, pinned gas environment — so when the SP1 re-execution slasher
lands, a wrong verdict becomes provably wrong without changing our contracts. The
honest label today is "AI-judged; attested by the Gas Killer operator set, not
proven; can only move on a real DKIM-signed alert"; after slashing it becomes
"optimistically verified" (rollup-grade).

**Does the model replace the regex well?** Measured on 480 adversarial alert subjects
over our 40 live markets (speculation, negation, questions, wrong office, hypotheticals,
partial steps, plus positives phrased outside the regex vocabulary):

| judge | accuracy (470 unambiguous) | false YES | false NO |
|---|---|---|---|
| **our current regexes** | **70.2 %** | **50** | 90 |
| Qwen3-0.6B (the model on-chain today) | 41.1 % | 277 | 0 |
| Qwen3-4B | 88.7 % plain / **94.3 % strict** | 30 / **3** | 23 / 24 |
| Qwen3-8B | 96.4 % / 96.4 % | 9 / **1** | 8 / 16 |
| Qwen3.5-35B-A3B (the other demo model) | **97.7 %** plain / 89.4 % strict | 2 / 0 | 9 / 50 |

Two things fall out. (1) **Qwen3-0.6B cannot be the judge** — it answers YES to
everything, including "The Morning: Your Wednesday Briefing"; no prompt style fixes
that. (2) **Our regexes have a false-positive problem we did not know about**: 50 of
280 hard negatives would settle a live market YES today ("Poll finds LeBron James wins
the White House in hypothetical 2028 matchup", "Hillary Clinton wins Democratic
nomination for New York governor", "Mike Pence wins Republican nomination for Indiana
Senate seat"). A 4B-class model already beats the regex on both error types; the
35B MoE is the natural on-chain target because its per-token gas is that of a ~3B
dense model (3B active parameters).

**The three real blockers** (none is our code):
1. **Prompt budget.** Even the most compact prompt — `Headline: "…"\nClaim: …\nYES or NO?`
   inside the chat scaffold — is 44–73 ids (median 57) on real-length alert subjects,
   i.e. ≈1.25 T gas on 0.6B: **over the 2^40 monolithic cap**. Any real judge prompt
   needs Gas Killer's *sharded* inference path (service #321 / sdk #57, open, and its
   validator gate is hard-wired to the chat `fulfil()` selector), or a lock-step change
   of the `UNBOUNDED_*` constants to 2^41+.
2. **Fleet.** Nothing judge-shaped can run against the public router today: the
   service defaults to `GK_SIM_PROFILE=chain`, overlay mounting (gas-analyzer #168) and
   the LLM e2e wiring (service #319) are open PRs, and both demo models are switched
   OFFLINE on the site. A prototype needs Gas Killer to run an unbounded+overlay Sepolia
   fleet for us, or our own 3-operator compose stack from the #319 branch.
3. **Ingress is permissioned.** `POST /tasks` needs a `gk_` API key minted by the
   operators; "permissionless settlement" would shrink to the finalize step and the
   regex/NO fallbacks. The JSON-RPC ingress (#317/#318) is a draft.

**Recommendation.** Do it as an *opt-in, additive* settlement mode on Sepolia using the
"oracle adapter" design in §3 (a singleton `LLMJudge` Gas Killer consumer beside an
almost-unchanged `HeadlineMarket`), staged as in §7. Independently of Gas Killer, fix
the regex false positives the corpus exposed (§2.4) — that is a day of work and
improves the live Gnosis board now.

## 1. What Gas Killer actually is (verified)

| Claim | Status | Evidence |
|---|---|---|
| Consumer inherits `GasKillerSDK`; `verifyAndUpdate` checks block freshness (≤ `blockStaleMeasure`=300), `transitionIndex+1 == count`, digest `sha256(transitionIndex, this, targetFunction, storageUpdates)`, ≥66 % stake per quorum; then raw `sstore`/`log`/`call` | ✅ | `solidity-sdk/src/GasKillerSDK.sol`, `StateChangeHandlerLib.sol`; site `reference.mdx` |
| Unbounded profile: simulate at 2^40 gas; payload priced (≤ 2^24 apply gas: ~22.1k/cold STORE + transport + dispatch + 250k BLS floor); **any number of STOREs/CALLs within budget**; `CREATE` rejected; the StateTracker slot is priced (not exempt) and reported separately | ✅ (merged: gas-analyzer #166, service #353) | `gas-analyzer/docs/UNBOUNDED_MODE.md`, `crates/core/src/sim_profile.rs` |
| "Single-slot commitment" is a consumer *pattern* (PR #51), not a gate rule | ✅ | `UNBOUNDED_MODE.md` ("not a prerequisite") |
| STATICCALLs inside a tracked function are allowed and never enter the payload; the LLM engine is reached by STATICCALL | ✅ | `prestate.rs:56,118`; `GasKillerChat.sol:104` |
| **A reverting tracked call yields nothing signable** | ❌ docs say so, code does not | `prestate.rs:74-76` → struct-log fallback keeps the root frame; the `trackState` counter bump **before** the body means a reverted `judge` still produces `[Store(counter, N+1)]`, operators sign it, and the task becomes `ready` — burning a transition index as a no-op. Design consequence: the judge must never revert; map every failure to an explicit `Abstain` write. |
| Qwen3-0.6B consumer: prompt **tokenized off-chain** (ids in calldata), on-chain tokenizer only *decodes*; chat template `<\|im_start\|>user\n…<\|im_end\|>\n<\|im_start\|>assistant\n<think>\n\n</think>\n\n`; `Qwen3.generate` only checks `id < vocab` — no canonical-tokenization check | ✅ (PR #56, open) | `GasKillerChat.sol`, `Qwen3.sol:655`, `tools/qwen3_float.py:164`; scaffold ids `[151644,872,198] … [151645,198,151644,77091,198,151667,271,151668,271]`; `YES`=14004, `NO`=8996, `Yes`=9454, `No`=2753 |
| Gas: 16-id prompt + 1 token = 344.8 B; +8 tokens = 545.1 B ⇒ ~21.5 B per prompt position, ~28.6 B per generated token (~4.5 B of which is the 151,936-row classifier); ~1 B gas/s on anvil (0.2–0.4 B/s on the shared Sepolia fork); 35B-A3B ≈ 170 B/position, 3.6 T per 8-token answer, ≈75 min sharded | ✅ (anvil measurements in README/RESEARCH.md; 35B numbers only on the live site) | `onchain-llm/README.md:107`, `RESEARCH.md:120`, `GasKillerChat35.sol:11`, llm.gaskiller.xyz constants |
| Sharded mode: segments run by k=2-of-N committees; each signer verifies the hash chain and **only the segments it ran**; committee agreement enforced by the router; VRF sortition, custody receipts, segment slasher are non-goals; the gate is armed only for a configured consumer address and keys off the `fulfil` selector | ✅ (open: service #321, sdk #57, gas-analyzer #172 draft) | `common/src/shard.rs verify_own_segments`, `docs/SHARDED_INFERENCE.md` on the PR branch |
| "native fast-executor" on the demo = `gk-fast-view`: the same Solidity bytecode AOT-compiled with revmc (LLVM) as a sidecar; bit-exactness vs the revm interpreter argued by golden-fixture differentials, not proven | ✅ | gas-analyzer #172 |
| **No slashing / fraud proof / bisection is deployed.** Main signs the 4-field digest; slasher = sdk #46→#66 + service #345 (open); the slashing spec docs referenced by `sim_profile.rs` do not exist on any branch; demo page's "Wrong results are slashable" is copy | ✅ | `example-contracts/SECURITY.md:26-27,93-96`; `gh pr view 66` |
| Ingress: `POST /tasks` (alias `/trigger`) requires `Authorization: Bearer gk_…`; keys minted in-cluster via `ADMIN_KEY`; no self-serve; tasks visible only to their key; 60 rpm; `call_data` ≤ 128 KiB (shared with `storage_updates` in the payload) | ✅ | `router/src/ingress.rs`, `common/src/task_data.rs:41,65` |
| Payload: router returns `{to,data,value,chain_id,estimated_gas,valid_until_block}`; **client signs and pays**; router validity = reference block + **50 blocks (~10 min)**, not 300; `TASK_TTL_SECONDS`=600; dedup only with explicit `transition_index`; `GET /tasks/{id}` re-validates (409 `PAYLOAD_EXPIRED`) | ✅ | `config.rs:712`, `executor.rs:614`, `ingress.rs:1006-1055` |
| Operators: **n = 3**, all Gas Killer's own GKE pods (`gas-killer-node-{1,2,3}`), registered 2026-05-29, 0.001 test-stETH each (0.003 total), one EOA `0x5DD2…634E` is owner/churnApprover/ejector of the RegistryCoordinator and owner of the AVS; consensus needs 3-of-3 off-chain (any pod outage halts), on-chain 66 % is met by any 2 | ✅ (Sepolia `cast` reads) | checker `0x6953…` → RC `0x0a03…`, IndexRegistry `totalOperatorsForQuorum(0)=3` |
| Chains: documented public AVS is Sepolia only; `TransitionGuard` needs EIP-1153 (Gnosis has Cancun since 2024-03-11); Schnorr scheme is chain-agnostic but its registry "holds no bond" (issue #65); **an undocumented Gnosis-mainnet BLS deployment exists** (bridged `RegistryCoordinatorMimic` fed by SP1Helios from Sepolia, operator snapshot frozen at Sepolia block 10,666,503 = 2026-04-15, last activity May 2026) | ✅ | `configuration.mdx`, `TransitionGuard.sol:26`, sdk broadcast 2026-04-20, service PR #114/#154 |
| Roadmap: "Permissionless onchain integration is out of scope… allowlisted ingress only" | ✅ | `roadmap/roadmap.html:509` |

## 2. Judge quality: the experiment

### 2.1 Corpus
480 breaking-news **email subjects** over the 40 live Gnosis markets
(`docs/polymarket-board.json`), 12 per market, in real outlet styles (NYT "Breaking
News: <sentence>", AP "AP News Alert: …", WSJ "News Alert: …", …), labeled with the
verdict a careful human resolver would give *from that one subject and the market's
description*. Mix per market: 4 positives, 1 indirect positive ("President-elect
LeBron James vows unity in victory speech"), 7 hard negatives — speculation ("poised
to", "weighs run"), negation ("ends bid", "calls off invasion"), question headlines,
wrong office ("wins Democratic nomination for New York Senate seat"), wrong entity
(Khloe Kardashian), hypothetical/poll ("Poll finds X wins the White House in
hypothetical matchup"), partial steps ("wins Iowa caucuses", "airstrikes" for an
invasion market). 10 items flagged ambiguous are excluded from accuracy. The corpus
was produced by five independent writer agents from the market descriptions; it is
synthetic, but the negatives are exactly the headline shapes newspapers send.
File: `.context/gk-corpus.json`; regressions: `.context/gk-regex-eval.mjs`.

### 2.2 Method — exactly the on-chain decode
`mlx-lm` on Apple silicon, Qwen3 chat template with thinking disabled (the same
`<think>\n\n</think>\n\n` scaffold the on-chain engine uses), **one forward pass, greedy
next token**. Two extractors: *argmax* (full-vocab argmax, what `Qwen3Engine.argmaxRange`
computes; verdict = YES/NO only if the top token is a YES/NO word, else ABSTAIN) and
*restricted* (argmax over the YES/NO ids only — a two-row classifier read, cheaper than
the full 151,936-row argmax). Weights: Qwen3-0.6B/4B/8B at **8-bit** (the on-chain model
is int8 per-row — same precision class; the on-chain Q24 activation path may differ on
the margin), Qwen3.5-35B-A3B at 4-bit (the 8-bit checkpoint is 37 GB; treat 35B numbers
as a lower bound). Harness: `.context/gk-judge-eval.py`.

Prompt styles: **baseline** (question + full resolution rules + subject; ~300 ids),
**default-no** (strict "default is NO" framing), **short** (`Headline: "…" / Claim: … / YES or NO?`; 44–73 ids — the only shape close to the
on-chain budget) and **short + instruction** (~85 ids).

### 2.3 Results (470 unambiguous items)

| judge (weights) | prompt (ids) | argmax accuracy | false YES | false NO | margin-calibrated* |
|---|---|---|---|---|---|
| **current regexes** (live board) | — | **70.2 %** | **50** | 90 | — |
| Qwen3-0.6B (8-bit, = on-chain model) | plain rules (~300) | 41.1 % | 277 | 0 | 63.4 % |
| Qwen3-0.6B | strict "default is NO" (~330) | 41.1 % | 277 | 0 | 65.1 % |
| Qwen3-4B (8-bit) | plain rules | 88.7 % | 30 | 23 | 90.4 % |
| Qwen3-4B | strict | **94.3 %** | **3** | 24 | 95.5 % |
| Qwen3-8B (8-bit) | plain rules | 96.4 % | 9 | 8 | 96.8 % |
| Qwen3-8B | strict | 96.4 % | **1** | 16 | 98.7 % |
| Qwen3.5-35B-A3B (4-bit) | plain rules | **97.7 %** | 2 | 9 | 98.5 % |
| Qwen3.5-35B-A3B | strict | 89.4 % | 0 | 50 | 98.9 % |
| every model | bare `Headline / Claim / YES or NO?` (44–73) | 58.9–61.1 % | 0–4 | 179–193 | 62.8–79.6 % |
| 4B / 8B / 35B | bare + one instruction line (~85) | 60.0 / 66.2 / 58.9 % | 0 | 188 / 159 / 193 | 90.9 / 94.3 / 90.6 % |

\* "margin-calibrated" = verdict YES iff `logit(YES) − logit(NO) > τ` with τ chosen on this
corpus (in-sample, so an upper bound); it shows how much signal the single forward pass
carries beyond the raw argmax. Full table incl. the "restricted" two-row extractor:
`python3 .context/gk-eval-summary.py`.

Per-kind accuracy of the best configurations and the regex:

| kind (n) | regex | 4B strict | 8B strict | 35B plain |
|---|---|---|---|---|
| positive (157) | 66 % | 90 % | 94 % | 97 % |
| positive-indirect (36) | **0 %** | 78 % | 81 % | 89 % |
| speculation (39) | 100 % | 100 % | 100 % | 100 % |
| negation (40) | 100 % | 100 % | 100 % | 100 % |
| question (40) | 95 % | 100 % | 100 % | 100 % |
| partial step (38) | 84 % | 92 % | 97 % | 100 % |
| wrong entity (39) | 85 % | 100 % | 100 % | 95 % |
| wrong office (24) | **42 %** | 100 % | 100 % | 100 % |
| past / hypothetical / poll (40) | **58 %** | 100 % | 100 % | 100 % |
| near-miss (17) | 71 % | 100 % | 100 % | 100 % |

Reading:
- **0.6B is a YES-machine** (277 false YES, 0 false NO) under every prompt; logit gaps
  between positives and negatives overlap completely. It is the model deployed on-chain
  today. Thinking mode would help but costs hundreds of generated tokens at 28.6 B gas
  each — not a settlement path.
- **4B is the knee.** Qwen3-4B with the strict prompt reaches 94.3 % with only **3 false YES** — the expensive error for a settlement oracle, since a wrong YES pays out while a wrong NO only waits for the next newspaper's email; 8B reaches 96.4 % with 1 false YES; the 35B MoE 97.7 % on the plain prompt. The strict framing trades false YES for false NO on every model (the 35B over-corrects to 50 false NO), which is the right direction for this use. Remaining 35B errors are genuine edge cases ('Ocasio-Cortez clinches nomination after Sanders endorsement' on the Sanders market; 'Obama accepts nomination to chair the convention').
- **The short prompt** (no resolution rules, just the claim) **collapses every model to NO** (58–66 %): asked `Claim: X has won … YES or NO?`, the models answer whether the claim is true *in the world* (it is not — 2028 has not happened), not whether the headline reports it; adding one instruction line (~85 ids) does not fix the argmax. The signal is still in the logits: a fixed margin τ on `logit(YES) − logit(NO)` recovers 90.9 % (4B) / 94.3 % (8B) on the ~85-id variant. Design consequence: a budget-constrained judge should read **two logits against a pinned threshold** (an engine view returning the two rows — cheaper than the full 151,936-row argmax) rather than take the argmax; τ is model- and prompt-specific, must be calibrated on held-out data and pinned as a protocol constant next to the manifest. Rules-bearing prompts (~300 ids) are what make the raw argmax work, and they are 6–7× over the monolithic budget.
- **Regex**: 70.2 % — 90 false NO (positives phrased outside the pattern: "CNN projects
  LeBron James will be the next president", "Winfrey crosses the 1,976-delegate
  threshold") and **50 false YES**, concentrated in hypothetical/poll (17), wrong office
  (14), wrong entity (6), partial (6).

### 2.4 A finding about the live board, independent of Gas Killer
The 50 regex false positives are real headline shapes. `(wins|clinches) … (Democratic|
Republican) nomination` patterns accept "wins Democratic nomination **for Indiana
Senate seat**"; `… wins the White House` accepts "**Poll finds** … wins the White House
in hypothetical matchup"; "If X wins the nomination, here is how…" explainer alerts
match outright. These markets are live on Gnosis with zero liquidity, so nothing is at
risk today, but the patterns should be tightened before anyone funds them (negative
lookahead is unsupported in `RegexLib`, so the fixes are anchored word-order
constraints plus exclusion of "poll", "if", "would", "hypothetical", "for … seat/
governor"). The corpus is a ready-made regression suite for that pass.

## 3. Integration design: `LLMJudge`, an oracle adapter beside `HeadlineMarket`

Three designs were drafted independently (minimal adapter; a Gas-Killer-native market
clone whose whole settlement lands as one `verifyAndUpdate`; a deployment-first plan)
and scored by two judges. The **adapter won on both cards** (38/50 and 36/50 vs 28–29 for
the others): it is the only design that needs zero new upstream Solidity, it keeps the
payload to `[STORE, LOG]` with only STATICCALLs (the cheap "prestate-net" extraction
path), and it keeps `ConditionalTokens.reportPayouts` in *our* transaction rather than
as a `CALL` op inside a signed payload. The native design was rejected for today
because per-clone `GasKillerSDK` puts `trackState` on every direct-call path (each
`submitEmail`/`resolveNo` invalidates in-flight judge payloads) and needs an exact
on-chain Qwen BPE encoder that does not exist; its one-tx UX and challenge-window ideas
are grafted below. Full texts: `.context/gk-designs.json`, scores `.context/gk-judges.json`.

### 3.1 Shape

```
             POST /tasks (api key)              verifyAndUpdate (bot signs, pays)
settlement ───────────────▶ Gas Killer router ───────────────────────────┐
   bot                      operators simulate judge() at 2^40 gas:      │
    │                        DKIMVerifier.verify (STATICCALL)            ▼
    │                        subject := parse(signed header)      ┌────────────┐
    │                        ids := tokenize(subject, criteria)   │  LLMJudge  │ verdicts[keccak(market, keccak(header))] = YES/NO/ABSTAIN
    │                        Qwen3Engine.chat(ids, 1) (STATICCALL)└─────┬──────┘
    │                                                                   │ verdictOf()  (view)
    └── submitProof(sourceIndex, proof) ───────▶ HeadlineMarket ◀───────┘
        re-verifies DKIM/domain/window/From/nullifier; contentMatches() asks the judge
        instead of RegexLib; K-th source ⇒ conditionalTokens.reportPayouts([1,0])
```

### 3.2 Contracts
- `contracts/src/judge/LLMJudge.sol` — singleton, `is GasKillerSDK` (template:
  `GasKillerChat.sol`). Immutables: engine, `weightsManifest` (overlay mode,
  `weightsRoot = 0`), packed config, our `verifier`, pinned template-fragment ids and
  YES/NO id sets (generated by a build step from `tokenizer.json`, pinned by a forge
  test against `tools/qwen3_float.py chat_ids`). Storage: one mapping
  `verdicts[keccak(market, headerHash)] → uint8(None|Yes|No|Abstain)`, first-wins.
  **Grafted:** an owner/multisig-guarded `setGasKillerConfig(avs, checker)` — the docs
  say the Sepolia operator set "is expected to change" and constructor-only wiring
  bricks every criteria market on the first rotation.
- Tracked `judge(address market, EmailProof proof)`: `verifier.verify(proof)`
  (STATICCALL); **extract the Subject from the RSA-signed header bytes itself**
  (`DKIMVerifier.contains(header, subject)` only proves `proof.subject` is *a
  substring* of the header — fine for a regex over a field the creator chose, fatal for
  a judge that could be handed "invasion of Iran" cut out of "rules out invasion of
  Iran"); read `market.criteria()` (STATICCALL); tokenize on-chain; `engine.chat(ids,
  maxNewTokens=1)`; map the single argmax id → Yes / No / Abstain; **every failure path
  (bad DKIM, missing criteria, subject contains `<|im_start|>`/`<think>` control
  strings, prompt over cap) writes `Abstain` instead of reverting** (§1: a revert still
  gets signed as a counter-only no-op). One STORE + one `JudgeVerdict` log carrying
  `(market, headerHash, verdict, answerId, promptIds, subject)` so anyone can replay.
- `HeadlineMarket.sol` (+~25 lines): `string criteria`, `ILLMJudge judge` appended to
  storage (strict layout extension; old clones untouched), `InitConfig.criteria`,
  creation rule "regex **or** criteria", and one branch in `contentMatches`:
  `if (pattern empty && criteria set) return judge.verdictOf(this, keccak(proof.header)) == Yes;`.
  `submitProof` is therefore the finalize call — it re-runs every cryptographic check
  in our own tx, so the Gas Killer payload never contains a `CALL`, and the verdict key
  (`keccak(header)`) guarantees the market can only consume a verdict about exactly the
  bytes it re-verified.
- `MarketFactory.sol`: `criteria` param, `judge` immutable. New factory on Sepolia;
  the 40 Gnosis markets are EIP-1167 clones of the old implementation and stay regex.
- `foundry.toml`: `evm_version = "cancun"`; `forge install gas-killer/solidity-sdk` at
  the PR #56 head (brings `eigenlayer-middleware`), copy `Qwen3Engine/Qwen3/DataContractLib`.

### 3.3 Prompt binding — the part that makes this non-trivial
In the demo, prompt token ids come from the browser and the contract only checks
`id < vocab`. For a judge the prompt must be a **pure function of the signed bytes**,
otherwise a submitter holding a float copy of the model can search over the
exponentially many byte-equal tokenizations of a real subject for one that flips the
verdict. Options, in order of preference:

1. **On-chain tokenization** of subject + criteria against the tokenizer table the
   overlay already mounts for decoding (`Qwen3Engine._decode` layout: raw-byte strings,
   151,936 entries). A greedy longest-match costs ≤ 0.5 B gas — trivial under the
   unbounded profile — but is *not* HF BPE (differs on rare words/punctuation: a quality
   cost, not a safety cost). The exact alternative is a byte-level BPE encoder with a
   merges blob — ~300 lines of Solidity plus a new tokenizer blob and manifest hash
   (gas-analyzer #168 constants); the same PR already ships a SentencePiece encoder for
   the Llama example, so the pattern exists. Recommended for v1; ask Gas Killer for the
   merges blob in the next manifest.
2. **Detokenize-and-compare** (ids in calldata, `keccak(detok(ids)) == keccak(subject)`):
   cheap, HF-exact, but leaves the segmentation to the submitter. Acceptable only if the
   *operators'* gate enforces canonical ids (sharded mode, §4), and then it is attested,
   not verified.

Verdict extraction: `maxNewTokens = 1`; id ∈ {14004 YES, 9454 Yes, (space variants)} ⇒
Yes; {8996, 2753, …} ⇒ No; anything else ⇒ Abstain. Only Yes moves the market. The
two-row "restricted" read would need an engine view (`judge(ids) → (logitYes, logitNo)`)
— cheaper than the full classifier (~4.5 B gas saved) and removes the Abstain case; it
is an engine change to request from Gas Killer, measured in §2.3 as equal or better.

### 3.4 Flow and failure modes
1. Creator opens a market with `criteria` (≤ ~120 bytes) and no regex; the app offers
   "plain-English criterion (AI-judged)" next to the regex writer and **previews the
   verdict in-browser** on the creator's example headlines with the same model
   (WebLLM already ships Qwen for the regex writer) — what you see is what settles, up
   to int8/float drift.
2. The settlement bot (`app/scripts/settlement-bot.mjs`, IMAP or `.eml`) builds the
   `EmailProof` as today; pre-screens with a float model so obvious NOs never spend a
   fleet round; `POST /tasks {target: LLMJudge, call_data: judge(market, proof)}` with the
   key; `transition_index` omitted ⇒ router assigns it (serialises the singleton).
3. Operators simulate (minutes, §4), sign; bot polls `GET /tasks/{id}`, signs the
   returned `verifyAndUpdate` and broadcasts **within the 50-block window** (cron every
   ≤10 min, not daily); ~0.35–0.5 M gas (one cold STORE + log + ~250 k BLS check).
4. Anyone (no key) calls `submitProof(sourceIndex, proof)` — ~2 M gas on the interpreted
   DKIM path — which consumes the verdict and, at the K-th source, reports payouts.
   Graft: a periphery `settle(payload, sourceIndex, proof)` that does 3+4 in one tx.
5. Failure: task `failed`/`expired` ⇒ resubmit (a new multi-minute round); verdict
   `No`/`Abstain` ⇒ that email is simply not evidence; **AVS down ⇒ the market resolves
   NO at `deadline + resolutionBuffer`** — a liveness failure that creators must price
   with buffers ≥ 3 days for criteria markets, and the reason to keep regex markets
   available as the no-dependency option.
6. Finality graft: pack `judgedAtBlock` into the verdict word and have `submitProof`
   wait N blocks, so that when the slasher exists a challenged verdict can be voided
   before it is consumed (`reportPayouts` is irreversible).

Throughput: the singleton's transition counter serialises verdicts globally — a few per
hour on the monolithic path, which is fine for breaking-news cadence but means a stuck
transition stalls every AI-judged market; the per-market clone variant fixes that at
the cost of the direct-call races above.

## 4. The prompt budget (the finding that reshapes the design)

| prompt | ids (median / max on our corpus) | 0.6B gas ≈ 21.5 B/pos + 28.6 B | 35B-A3B ≈ 150–450 B/pos |
|---|---|---|---|
| bare short (`Headline / Claim / YES or NO?`) — **does not work** (§2.3) | 57 / 73 | 1.25 T / 1.6 T | 9–26 T / 11–33 T |
| short + instruction, margin-read — minimum that works | ~85 / 100 | 1.85 T / 2.2 T | 13–38 T / 15–45 T |
| baseline (question + rules + subject) | ~307 | 6.6 T | 46–138 T |
| 2^40 cap per tracked call | — | **1.10 T** | 1.10 T |

So the monolithic consumer (`GasKillerChat.ask` shape) fits **at most ~49 ids including
the 12-id scaffold**, and the most compact judge prompt over a real NYT-length subject
is already over it. Ways out, each needing Gas Killer:
- **Sharded path** (service #321 / sdk #57): the 2^40 cap is per *segment*, prompt length
  is bounded by the 1024 context and wall-clock (~2 min inference + 1 round for 24
  positions on 0.6B ⇒ minutes for 60; 35B ≈ 75 min per 24 positions ⇒ **hours** per
  verdict). Requires a judge-shaped consumer `fulfilJudge(market, proof, answerIds,
  pipelineRoot)` and a validator gate that (a) accepts it and (b) **recomputes the
  canonical prompt ids from the DKIM-bound subject** before signing — binding moves
  into the attested layer. This is the realistic path and the only one that reaches
  the 35B.
- **2^41+ constants**: a lock-step fleet + (future) SP1-guest change; doubles the cap,
  still too small for rules-bearing prompts.
- **Prefix resume** (`settlePrefix`/`fulfilResumed`): amortises the fixed scaffold and a
  system prompt; the per-market part still has to fit.

Model choice given that: 0.6B is out on quality; Qwen3-4B is the same dense
architecture as the 0.6B engine (`Qwen3.sol` is parameterised by a packed config; 4 GB
int8 overlay) at ~7× the gas; **Qwen3.5-35B-A3B is already built (`Qwen35.sol`) and its
3B-active MoE costs roughly a 3–4B dense model per position** — the best quality per
gas — but at ≈0.8 B gas/s it is hours per verdict and it is currently offline. Either
way the judge is a sharded-mode consumer; plan for verdict latency of 30 min–3 h and
size `resolutionBuffer` accordingly.

## 5. Trust, stated precisely

| property | how it is guaranteed |
|---|---|
| The email was sent by the named newspaper under a registered DKIM key, in the window, from a matching address, never used before | **Cryptographic, on-chain, in our tx** (`DKIMVerifier`, `submitProof`) — unchanged |
| The judged Subject is the literal `subject:` line of those signed bytes | Cryptographic, given §3.2's header parsing, keyed by `keccak(header)` |
| The prompt is a pure function of (signed subject, criteria, pinned template, pinned manifest) | Cryptographic on the monolithic path (on-chain tokenization); **attested** on the sharded path |
| The model is fixed and the computation deterministic (int8/Q24, greedy argmax) | Cryptographic commitment (32-byte manifest) + bit-exact integer spec (`tools/qwen3_int.py`, forge-pinned) |
| `verdicts[key]` equals what `judge()` computes | **Attested** by ≥66 % of a 3-pod quorum run by one organisation with 0.003 test-stETH; no re-execution, challenge, or slashing exists. After sdk #66 / service #345 + the SP1 guest binding of the 2^40 env and overlay set (`chainConfigHash`): **fraud-provable**, and this design needs no change because `judge` reads no block env / `msg.sender` and all inputs are calldata or immutable. |
| Liveness | Depends on the API key, the fleet running `unbounded` + overlay, router uptime, and the 50-block payload window; worst case = NO at deadline + buffer |

Comparisons: the current regex path is fully objective on-chain (the only trust is the
DKIM key's provenance — see `PINNED-KEY-MARKETS.md`). UMA is human-optimistic with a
token vote. This is machine-optimistic-to-be: objective rule, attested execution,
provable later. It is strictly *more* trusted than the regex path today and *more
expressive*; do not describe it as trustless until the slasher is live, and do not put
real value behind it before then (Gas Killer's own guidance).

Residual attack surface: model error (honest-but-wrong is indistinguishable from malice
on-chain — mitigated by the creator's in-browser preview and by ABSTAIN on weird
outputs); prompt injection via a newspaper subject (control-token rejection; newspapers
are already trusted in this system); griefing the singleton's counter or burning fleet
minutes with junk `judge(market, …)` calls (bounded by API keys; require `market` to be a
factory-registered address); `DKIMVerifier.contains` substring hole on the regex path
(separate fix: parse the header there too).

## 6. Deployment reality

- **Sepolia first**: both our stack (`deployments/sepolia.json`) and the AVS
  (`AVS 0xdCec…eeD9`, checker `0x6953…5b9`) are there. Needs a fleet with
  `GK_SIM_PROFILE=unbounded`, prestate-net encoding, the 0.6B/35B overlay mounted,
  `ROUND_TIMEOUT` ≫ simulation time (helm default 300 s; #319 raises it), and
  `TASK_TTL_SECONDS` above the round. Alternative: run the #319 compose stack ourselves
  (3 operators on an anvil fork, `tools/deploy_anvil.py --overlay`) — good enough to
  prove plumbing, worthless as trust.
- **Gnosis** (where the 40 markets live): no EigenLayer. Gas Killer's own answer is the
  SP1Helios-bridged `RegistryCoordinatorMimic` deployment (undocumented, snapshot frozen
  since April, parity PR #154 open); Schnorr is chain-agnostic but its registry has no
  bond; the Gnosis AMB adds a validator-multisig trust hop. None is "trustless"; the
  honest Gnosis story is "after Sepolia, when the bridged mimic is maintained".
- **Ingress/bot**: one `gk_` key for the settlement bot; `settle.yml` cron to ≤10 min;
  persist `task_id`s; payload re-fetch via `GET /tasks/{id}` only.
- **Rotation**: operator-set redeploys change the checker; keep `setGasKillerConfig`
  guarded by a multisig; sdk #66 changes the signed digest (breaking) — plan a judge
  redeploy + factory pointer.

## 7. Staged plan

0. **Now, no Gas Killer** — tighten the regexes the corpus broke (§2.4); commit the
   corpus as `test/fixtures/headlines/` and a differential test; parse the Subject from
   the signed header in `DKIMVerifier` (closes the substring hole for both paths).
1. **Plumbing prototype (Sepolia, local #319 stack, 0.6B)** — `LLMJudge` + market/factory
   changes + bot; prove: single-STORE payload shape (`vm.record`), `verifyAndUpdate`
   applies a verdict, `submitProof` consumes it, header parsing fuzz, template-id pins.
   Accept that 0.6B verdicts are noise.
2. **Land the Gas Killer side** — the whole LLM stack (sdk #56/#57, service #319/#321,
   analyzer #168, the JSON-RPC ingress #317/#318) is our own open branches, so this is
   self-unblocking rather than a vendor ask: (a) a judge-shaped sharded consumer + gate that recomputes
   canonical ids from calldata bytes, (b) a served Qwen3.5-35B-A3B (or Qwen3-4B)
   unbounded fleet on Sepolia, (c) a merges blob in the tokenizer manifest, (d) a
   two-row logit view. Replay our 480-item corpus through the *integer* engine on anvil
   to get on-chain-exact accuracy (the numbers in §2 are float/quantised proxies).
3. **Opt-in "AI-judged" markets on Sepolia** with the trust badge wording from §5, a
   `judgedAtBlock` challenge-window field, buffers ≥ 3 days, in-browser verdict preview.
4. **Real value only after** the slasher (sdk #66, service #345, SP1 guest with the
   unbounded/overlay `chainConfigHash`) is deployed and the operator set is more than one
   organisation; then revisit Gnosis via the maintained bridge.

A cheaper hybrid worth considering at stage 3: **regex AND judge** — the regex keeps
liveness independent of the AVS for clear positives, and the LLM acts as a *veto* that
removes the false-YES class the regex cannot express (polls, wrong office). It never
adds a dependency for a NO and cuts the regex's 50 false YES without waiting for
sharded inference to be fast.

## Appendix — reproduction
- `.context/gk-brief.md` — facts sheet given to the analysis agents.
- `.context/gk-verdicts.json` — 10 adversarial claim checks with file:line evidence.
- `.context/gk-designs.json`, `gk-judges.json` — three designs, two score cards.
- `.context/gk-corpus.json` (480 items), `gk-regex-eval.mjs`, `gk-judge-eval.py`
  (`PROMPT_STYLE=baseline|default-no|short`), `gk-eval-full.sh`, `gk-eval-summary.py`,
  outputs `full-out-*.json`. Models: `mlx-community/Qwen3-{0.6B,4B,8B}-8bit`,
  `mlx-community/Qwen3.5-35B-A3B-4bit`.
- Gas Killer sources cloned at `.context/gaskiller/` (solidity-sdk main + PR #56 worktree,
  service, gas-analyzer, example-contracts, site, infra, roadmap).

## 8. Implementation (2026-08-22) — built against an assumed live 35B fleet

Everything below is in the repo and tested; it assumes Gas Killer provides a fleet running
the sharded Qwen3.5-35B-A3B path (service #321 + sdk #57, `GK_SHARD_CONSUMER` = our judge,
`GK_SIM_PROFILE=unbounded`, the 35B overlay mounted) — nothing here needs a Gas Killer code
change, and the validator gate is used exactly as written.

### 8.1 Design decisions that changed from §3
- **Selector-identical consumer.** `LLMJudge.fulfil / fulfilResumed / settlePrefix` have
  exactly the `GasKillerChat35Sharded` signatures (`0x9c98c06e / 0x6c4d43bc / 0x7e8de12c`,
  asserted in tests), so the unmodified gate accepts them. The tracked call is *not* a pure
  commit like the chat consumer's: it detokenizes the prompt ids, **re-tokenizes
  canonically** and checks equality, so a submitter cannot pick a segmentation; but it never
  runs the model and never reverts on bad input (it logs `JudgeRejected`), because the
  analyzer signs a counter-only payload for a reverted simulation (§1).
- **Binding moved to the market.** No DKIM inside the judge. Verdicts are keyed by
  `keccak256(promptText)`; `HeadlineMarket` rebuilds the text from its own `question` +
  `criteria` and the Subject it parses out of the **RSA-signed header** (RFC 2047 B/Q
  decoded — newspapers B-encode subjects — `JudgePrompt.subjectFromHeader`), never from
  `proof.subject`. So a verdict can only move a market for a genuine, in-window email of a
  configured source; the judge is a generic text→verdict oracle anyone can query.
- **Prompt = the full-rules prompt** (97.7 % on the corpus; the compact variants lose
  3–8 points: mid 89.4 %, mid+criteria 94.3 %). `criteria` carries the resolution rules
  (≤ 1200 bytes, one line). Prompts are ~270 ids, which forces **prefix resume**: the
  per-market prefix (scaffold + rules, up to the subject's opening quote) is warmed once via
  `settlePrefix`; each email then pays only for `subject + closing instruction` (~35 ids).
  The canonical tokenization is therefore *piecewise*: `scaffold ++ greedy(prefixText) ++
  greedy(tailText) ++ scaffold-suffix`, split at the first occurrence of the template's
  subject lead-in (question/criteria may not contain a newline, enforced at creation).
- **Canonical tokenizer = greedy longest-match over the on-chain decode table** (ties →
  lowest id, ids < 248044 so no control token can be produced), implemented in Solidity
  (`TokenTable`, first-byte bucket index; ~12 B gas for a 270-id prompt including the
  2.8 MB table read — trivial under the 2^40 profile) and mirrored in JS
  (`app/scripts/judge/tokenizer.mjs`); the two are differentially tested on real prompts.
  {{GREEDY_RESULT}}
- **Fleet parameters the bot must send** (all caller-supplied in `POST /shard/infer`):
  `model: "qwen35"`, `max_new: 1`, `seq_cap: 512` and the packed-config word 0 with
  `seqCap` rewritten to 512 (the demo pins 64), `stages: 10` (35B stage bounds snap to
  full-attention boundaries: 40 layers / 4). A ~235-id prefix warm needs the fleet's
  `GK_SHARD_GAS ≥ 2^42` (per-segment view-call gas, default 2^40); per-email resumed
  segments fit the default.

### 8.2 What is in the repo
| Piece | Where | Status |
|---|---|---|
| Vendored Gas Killer SDK (BLS) + minimal middleware types | `contracts/lib/gas-killer-sdk/` (commit in `VENDORED_COMMIT`) | builds under `evm_version = cancun` |
| `LLMJudge` consumer, `ILLMJudge`, `JudgePrompt`, `TokenTable` | `contracts/src/judge/` | 18/18 tests |
| Judged mode in `HeadlineMarket` (`criteria`, `judge`, `judgedVerdict`, `promptKeyFor`, `checkProof` reasons) and `MarketFactory` (`criteria` param, `judge` immutable) | `contracts/src/market/` | existing 73 tests still pass; storage is a strict extension, live clones untouched |
| Real 35B tokenizer table fixture (2.8 MB, byte-identical to the converter's blob) | `contracts/test/fixtures/qwen35/` | used to mount the overlay in tests/e2e |
| Pins (manifest `0x7bdf…1fa9`, chunk counts, scaffold/YES/NO ids) | `contracts/script/Qwen35Pins.sol`, `app/scripts/judge/tokenizer.mjs` | single source of truth, keep in sync |
| Sepolia deploy: judge wired to AVS `0xdCec…eeD9` / checker `0x6953…5b9` (env-overridable), factory with judge, seeded AI-judged Iran market | `contracts/script/DeploySepolia.s.sol` | fork-simulated, 33.6 M gas; CI deploys on push |
| Local deploy with a mock quorum | `contracts/script/Deploy.s.sol` | |
{{BUILDOUT_ROWS}}

### 8.3 Test coverage (contracts/test/LLMJudge.t.sol)
The test IS the operator: it mounts the real tokenizer table at the derived overlay
addresses, simulates the tracked call, extracts the storage diff + log the way the analyzer
does, applies it through `verifyAndUpdate` with a mock quorum, then has the market consume
the verdict for a real DKIM-signed fixture email. Covered: table mount/readback; greedy
tokenizer == JS mirror on a full prompt and detokenize round-trip; no special ids ever
produced; RFC 2047 B/Q/latin1 subject decoding and unsupported charsets; control-text
rejection; direct call without overlay reverts (counter never bumped); YES verdict →
`submitProof` succeeds; NO verdict → `checkProof` "judge verdict: NO"; no verdict → "no judge
verdict for this email yet"; non-canonical tokenization / smuggled `<|im_start|>` / wrong
`maxNewTokens` / unparseable answer / already-judged → `JudgeRejected` and no write; prefix
warm → resumed verdict; prefix mismatch / unsettled prefix rejected; judged-market creation
validation; owner-guarded `setGasKillerConfig`.

### 8.4 Gas/latency on the fleet (estimates)
Prefix warm per market: ~235 positions × ~150 B gas ≈ 35 T simulated, split over 10 stage
segments (needs `GK_SHARD_GAS ≥ 2^42`), once. Per email: ~35 positions ≈ 5 T simulated +
one argmax ⇒ ~1–2 h on the demo fleet's throughput; `verifyAndUpdate` ≈ 0.35–0.5 M gas on
Sepolia; `submitProof` (RSA-4096 + subject parse + bookkeeping) ≈ 2 M. Creators should set
`resolutionBuffer ≥ 3 days` on AI-judged markets (the seed uses 3 days).
