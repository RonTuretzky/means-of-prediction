# Peace settlement gas profile and authentication boundary

Worktree: `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach`.
Private audit root: `/Users/wk/.local/share/means-of-prediction/peace-gas-profile-20261021/`.

## Decision

Do not adopt a purported GasKiller authentication offload under the existing guarantees. The existing SDK can authorize updates in its own target storage, but cannot write the separate plain evidence gate. Calling that gate executes its full verification again. Making the gate a nested SDK target would give the quorum authority to replace its authentication checks with storage updates. That is an additional trust assumption, even though model results and consumer SDK storage already trust the quorum.

All original contract code, frozen source-policy/model/profile/request pins, genuine model and relay certificates, previous comparison artifacts, and tests are preserved. The new repository files are diagnostic tooling and this report. No new deployment or authenticated-preparation implementation is adopted.

## Matched historical transactions

The exact saved transaction calldata was replayed from local block 129, hash `0xe02bc89880aa8b1ae6b1be33b4b34d3b63496d70078a58d7c6d38f1e637ebea4`, at final timestamp 1792546544 (2026-10-21 01:35:44 UTC), sender nonce 27. Each alternative starts from the same state. The canonical comparison uses Cancun on an isolated Anvil chain 31337, forked only from an owned local archived node at that exact block, with synthetic balances, zero gas price, a 1-billion-gas block limit, and relaxed contract-size limits. No external fork/RPC is used. It establishes no default-chain feasibility or production settlement.

| Route | Final transaction gas | Calldata bytes | Cancun intrinsic gas |
|---|---:|---:|---:|
| Original direct finalize | 125,369,240 | 215,556 | 2,720,664 |
| Ordinary direct through sealed calldata cache | 123,935,796 | 4 | 21,064 |
| Same cache through genuine GasKiller certificate | 124,075,906 | 1,156 | 30,148 |

The cache contains the exact complete packet; it is not an authenticated-fact cache. Both relay routes still call the original full finalizer. The certified route costs 140,110 gas more than ordinary cached direct. Its 1,293,334-gas reduction versus uncached direct is a complete-route difference involving transport and warmed accesses, not evidence that RSA/MIME verification was offloaded.

The prior comparison remains immutable at `docs/HANDOFF-PEACE-ANVIL-COMPARISON-20261021.md` and `/Users/wk/.local/share/means-of-prediction/peace-anvil-comparison-20261021/`. This profile does not regenerate the model executions or certificates.

## Attribution method

The new `app/scripts/laya-demo/peace_native_gas_profile.mjs` completes the three exact transactions, validates their original gas/hash and resulting consumer/gate state, and records native call traces. `peace_gas_profile.mjs` produced one completed detailed direct trace; the following redundant detailed runs were stopped deliberately. That direct trace contains 33,332,160 executed instructions in 22,513 distinct address/PC rows and took 454.518 seconds. Its receipt gas and call tree match the canonical direct replay.

`peace_source_gas_tracer.mjs` derives exclusive opcode gas from consecutive same-frame remaining-gas readings, subtracting child-frame gas. It deliberately does not use Anvil's `log.getCost()`, which did not reconcile in the preliminary probe. Terminal instruction costs reconcile to frame totals. Precompile gas remains separate from parent CALL overhead. Intrinsic calldata gas is independently computed and separated from the root call frame. Direct reconciliation is 122,520,448 opcode gas + 128,128 precompile gas + 2,720,664 intrinsic gas = 125,369,240 receipt gas.

The private `call_tree_profile.py` produces exact non-overlapping frame accounting. `source_map_profile.py` verifies deployed runtime bytecode against the unchanged compiled artifacts, masks only compiler-declared immutable slots, verifies the local source bytes against compiler metadata Keccak-256, then maps PC rows using UTF-8 byte offsets. Via-IR optimization can assign code to broad contract spans or shared helpers. Those residuals remain explicit; a source-span bucket is not an exact semantic function-call measurement.

The profiling result and final test/checkpoint files listed below are authoritative for completion. Preliminary diagnostic failures remain in the private directory; do not count them as successful tests.

## Measured stages

These are non-overlapping **exclusive** call-frame totals. Intrinsic gas is removed from the root consumer/relay frame and shown separately. The three columns each sum to their receipt; inclusive call costs must not be added to this table.

| Component | Direct | Cached direct | GasKiller certified |
|---|---:|---:|---:|
| Transaction intrinsic/calldata | 2,720,664 | 21,064 | 30,148 |
| Plain gate: header policy, MIME/body, commitments, bundle/nullifiers | 114,922,617 | 114,933,159 | 114,939,966 |
| DKIM verifier code, excluding child key/precompile calls | 6,841,011 | 6,838,511 | 6,838,511 |
| DKIM key registry | 38,092 | 42,115 | 46,138 |
| SHA-256 precompile | 106,284 | 106,284 | 106,716 |
| RSA modexp precompile | 21,844 | 21,844 | 21,844 |
| Consumer code, excluding child calls | 707,550 | 832,185 | 855,321 |
| Schnorr registry, excluding child calls | 11,178 | 14,356 | 19,843 |
| ecrecover precompile | 0 | 0 | 3,000 |
| Sealed calldata cache | 0 | 579,618 | 580,473 |
| Relay code, excluding child calls | 0 | 546,660 | 633,946 |
| **Total** | **125,369,240** | **123,935,796** | **124,075,906** |

The original direct `consumeBundle` frame costs 121,927,989 inclusive. Its four header-only DKIM verifier children cost 6,902,435 inclusive: BBC 1,745,165; CNN/ABC/RFI 1,719,090 each. Every route still executes four verifier calls and four RSA precompile calls. The lower inclusive verifier gas in the relay routes reflects warmed accesses; it does not establish skipped authentication.

The direct-only source map identifies **at least 44,707,090 gas** in the body/MIME/transfer group. Clearly mapped header policy is 1,859,684 and RSA/header binding is 2,258,922. These source-label figures are supporting attribution, not additional gas on top of the table. A further 44,882,152 gas maps to whole-contract spans, 20,340,649 to generated/dispatch code, and 8,291,384 to shared header/body helpers: **73,514,185 cannot be reliably divided by semantic stage**. In particular, the small explicitly mapped nullifier bucket does not mean storage writes are almost free; optimized writes may fall in the unresolved buckets.

The actual RSA and SHA-256 precompiles together use 128,128 gas in direct settlement, about 0.10% of its total. The large expense is surrounding Solidity validation/parsing and data handling. Optimize those loops with preserved semantics and differential malformed-input tests before assuming RSA arithmetic is the bottleneck.

## Validation and replay-environment repair

The serial targeted command passed **121 tests, 0 failed, 0 skipped**, across the unchanged five suites. Log: `profile-preserved-121-serial-tests.private.log`. This includes the genuine matched positive/replay and the existing malformed full-body/window/input/token, source/policy/model/request binding, missing/duplicate/conflicting source, expiry, revoked Google key, committee drift, corrupt cache, changed verifier code, wrong chain, certificate mutation and signed-anchor-age checks. The original BBC-only case still cannot meet the four-report source policy.

All three canonical transactions yield the same original consumer/gate state: Yes, source mask 15, four A-only observations, and exactly four request plus four email nullifiers consumed. Final relay nonce and transition counter are both 1. Final outcome commitment is `0x1d471043b19975aab91a1716396ac07850fb22a94c679cb2e5fd109e74de4b55`. All 70 protected prior files are byte-identical.

Two diagnostic infrastructure failures are retained, not hidden:

1. The first detailed tracer hit Node/Undici's default five-minute HTTP-header deadline. A concurrent fork-suite setup timed out while that trace monopolized Anvil; 112 local tests passed in that attempt, but it is not the successful 121-test result. The leaner tracer and explicit bounded `node:http` request completed the direct trace; the final tests ran serially.
2. Plain `anvil_loadState` restored the RPC block header but did not restore the matching EVM BLOCKHASH lookup. The preliminary certified transaction correctly reverted `BadAnchor` at 87,207 gas. RPC returned the genuine `e02bc...` block hash while EVM returned `535306...`. The canonical environment forks an owned local archive at `http://127.0.0.1:19546`, block 129, from the replay node at port 19545. Its EVM BLOCKHASH now matches the genuine saved anchor. This was checked using a read-only scratch-code call in a temporary empty block 130, then reverted before the matched transactions. No relay/gate state, contract code, certificate, or anchor check was overridden. The same original certified calldata then succeeds at exactly 124,075,906 gas.

Use `profile-final/` for canonical three-route receipts and call trees. `profile-native/` is the provisional load-state attempt and includes the rejected certificate. `profile-v2/` contains the completed direct opcode trace; its later branch was intentionally stopped. These distinctions are recorded in the final checkpoint.

## Existing costs that must remain separate

| Prerequisite from the preserved comparison | Gas |
|---|---:|
| Common contracts, Google key and operator setup | 18,871,071 |
| Four actual model certificate transports | 1,705,364 |
| Four full authenticated observation transactions | 125,339,203 |
| Common prerequisite subtotal | 145,915,638 |
| Sealed packet publication | 48,116,567 |
| Relay deployment | 59,482,439 |
| Cache and relay subtotal | 107,599,006 |

Including those prerequisites, the original lifecycle totals remain 271,284,878 direct, 377,450,440 cached direct, and 377,590,550 certified. Relay deployment includes an avoidable 215,552-byte copy loop. These costs were not charged again or silently omitted from the comparison. Model CPU execution is not included as EVM model inference gas.

## Precise execution boundary

1. `StateChangeHandlerLib.sol` in `/Users/wk/Documents/Codex/2026-10-21/task-3/example-contracts/lib/solidity-sdk/src/` implements STORE as local `sstore(slot,value)`. It has no arbitrary target-storage parameter. Its CALL executes the callee normally and bubbles failure.
2. `/Users/wk/Documents/Codex/2026-10-21/task-3/gas-analyzer/crates/core/src/trace.rs` retains ordinary external CALLs and excludes their internal effects from separate optimization because they will execute inside that call. The gate's nullifiers are separate-contract storage.
3. The real nested SDK/analyzer/service path requires integrated nested targets and frame/root/caller/transition acknowledgement. The current plain gate has no such interface. Integrating it would authorize quorum-signed effects in the authentication gate; the signature proves quorum authorization, not RSA/MIME computation correctness.
4. The current relay's typed receipt binds chain, consumer, packet, code, prestate, execution block/time, expiry, outcome and nonce. It then calls the unchanged finalizer. Snapshot binding protects context; it does not replace the full current authentication check.
5. An authorized malicious SDK quorum can already corrupt consumer SDK storage or its decision. It cannot directly consume the independent plain gate's request/email nullifiers. Preserve that distinction; a consumer `Yes` flag alone is weaker evidence than the whole verified gate state.

The complete code-level audit and proposed invariants are in `boundary-audit.private.md` and `prepared-auth-safety.private.md` under the private audit root.

## Proposed next experiment, not implemented

Use a separately versioned **plain onchain authenticated-preparation gate**. Have that gate perform the full original RSA/header/MIME/excerpt/input/token verification once, recording a write-once commitment to the exact request and all proof bytes. A consumer observation flag or quorum-signed success bit is insufficient. Preparation must not consume evidence or assert model support. A new consumer/request domain requires genuine certificates for that new context; existing signatures cannot be rebound to a new address or presented as new execution artifacts.

At finalization, freshly enforce the same actual block clock, signed t/x and Date bounds, request expiry, live Google key validity and identical key material, code/dependency identity, current committee snapshot/threshold, exact four ordered admitted sources, actual A-only model observations, no B/conflict, and all replay/nullifier conditions. Consume all eight nullifiers atomically only after every check succeeds. Existing source independence, source-policy/model/profile/request bindings remain fixed.

If preserving the current finalization tamper tests, retain full arguments and hash every complete EmailProof, input and token ABI against the gate-owned prepared commitments. A proof-free API changes the attack surface: body/window mutations must fail during preparation, and those old final-argument tests cannot be claimed unchanged. A cache-corruption negative remains applicable only if that route still reads the sealed cache.

Measure original direct, prepared ordinary direct and identically prepared GasKiller from matched states; report preparation storage/authentication and deployment costs as well as finalization and lifecycle totals. This is reuse of verification already performed onchain, not GasKiller-specific authentication offload. A succinct execution proof could offer another trust-preserving route, but no such prover/verifier exists in the inspected integration. Neither proposal is implemented or assigned a gas saving here.

## Limits that remain

- This is one retrospective, case-specific positive demonstration for market 5371292 and the fixed BBC/CNN/ABC Australia/RFI packet, not a measured general settlement accuracy rate or a generic publisher-count rule.
- Google DKIM authenticates relay bytes, not publisher authorship or the truth of the excerpt. Qualitative source admission remains a separate, frozen review. Archived non-DNSSEC key material does not itself prove historical DNS ownership; the actual market-close/first-receipt chronology is unresolved.
- The actual frozen model execution certificates remain genuine prior artifacts. They are quorum statements about execution, not a cryptographic proof of full-model inference or tokenizer semantics. Threshold 550,000 PPM and all model/profile pins are unchanged; absence does not become No.
- No production chain, live AVS, funds, credentials, paid RPC, new model run, mailbox operation, GitHub issue 4 comment, commit or push is involved.

## Files for continuation

- New private root: `/Users/wk/.local/share/means-of-prediction/peace-gas-profile-20261021/`.
- `protected-baseline-pins.private.json`: 70 prior files that must remain byte-identical.
- `restored-anchor.private.json`: restored local historical block/state guard.
- `profile-final/profiling-plan.private.json`, `profile-final/profiling-results.private.json`: canonical three-route plan and completion record.
- `profile-final/profile-*-transaction.private.json`, `profile-final/profile-*-receipt.private.json`, `profile-final/profile-*-state.private.json`: canonical actual transactions and state checks.
- `profile-final/profile-*-calls.private.json`, `profile-final/call-tree-*.private.json`: native call trees and exact non-overlapping profiles.
- `profile-v2/profile-uncached-direct-opcodes.private.json`, `profile-v2/source-map-uncached-direct.private.json`: completed direct-only opcode/source attribution.
- `canonical-three-route-stage-profile.private.json`, `direct-stage-reconciliation.private.json`: compact measured-stage reports.
- `profile-preserved-121-serial-tests.private.log`: successful complete test run; earlier similarly named log contains the recorded infrastructure failure.
- `final-live-state.private.json`, `final-local-fork-dump.private.json`, `root-engineering-checkpoint.private.json`, `cleanup.private.json`: terminal state, checkpoint and owned-node cleanup.
- `verified-bytecodes.private.json`: independent original-code receipt for offline source mapping.
- `boundary-audit.private.md`, `prepared-auth-safety.private.md`: execution boundary and proposed preparation design.
- Previous immutable comparison root: `/Users/wk/.local/share/means-of-prediction/peace-anvil-comparison-20261021/`.

All raw email/fixture/calldata and execution details stay private. Public source/report files contain no credentials or copied mail bodies.
