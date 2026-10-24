# Nobel Peace full-authentication Anvil comparison

Worktree: `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach`.
Private receipts and fixtures: `/Users/wk/.local/share/means-of-prediction/peace-anvil-comparison-20261021/`.
This is a separate continuation of `docs/HANDOFF-PEACE-CONSENSUS-20261021.md`; it preserves the original 112-test baseline, four genuine model certificates, selected source packet, model/profile/threshold pins, and the failed BBC-only source-admission example.

## Scope and frozen experiment

The authorized experiment uses only a synthetic local Anvil chain and three forks of that localhost chain. It does not use a public RPC, real wallet, real funds, production AVS, new evidence, retraining, deployment to a public chain, or the canceled GitHub issue comment. It is a retrospective replay at timestamp 1792546544, not a claim that evidence arrived before the real market resolved.

All three final routes start from the same block-129 state, with the same sender nonce and block-130 timestamp. They use the unchanged original consumer and evidence gate:

1. Original `consumer.finalize` with the full exact packet in transaction calldata.
2. `relay.directExecute`, loading identical calldata from a sealed immutable cache and calling the same original finalizer.
3. Actual Schnorr SDK `verifyAndUpdate`, authenticating a genuine aggregate certificate and invoking a typed callback that again calls the same original finalizer.

The third route uses genuine coordinator/participant signing code plus an explicit local EVM validator adapter. Each of three operators independently executes the complete call on its own Anvil fork. This is not a claim that the production gas analyzer automatically converts this cross-contract flow into cheap storage writes. The certified callback repeats all original onchain authentication and separate evidence-gate state changes.

The existing four model certificates are common prerequisites in every route. The model is not run in the EVM in any route. The new certificate covers full EVM finalization execution, not fresh model inference.

## Why the exact calldata cache exists

The finalization packet is 215,556 bytes, keccak256 `0x3dee100be9742fd6f65d80b2a7a1471ab3c0ce768977f97754618d90e402849f`. It exceeds the unchanged 131,072-byte task wire bound. Nine STOP-prefixed code shards hold the exact packet; each chunk is at most 24,575 bytes. Seal and read verify the complete packet hash, length, shard code hashes and manifest. The cache transports bytes and does not authenticate facts in place of the original gate.

A cheap storage patch to the consumer would not reproduce writes in its separate plain evidence gate. Skipping the full original RSA/body/source/time/request checks would change the comparison's security assumptions. Therefore no such shortcut is counted as successful settlement or acceleration here.

## Local profile and chronology

Anvil 1.5.1-stable, Cancun, chain ID 31337, 1,000,000,000 block gas, 900,000,000 transaction gas budget, 131,072 code-size limit and 1 GiB memory limit. The increased local code limit also permits otherwise oversized initcode. The gate runtime is 30,646 bytes, exceeding the ordinary 24,576-byte EIP-170 limit; the original consumer constructor with arguments is 59,935 bytes, exceeding the ordinary 49,152-byte initcode limit. These are explicit relaxed experimental settings, not production feasibility evidence.

Root RPC is `http://127.0.0.1:19545`. Operator forks use ports 19546, 19547 and 19548 and fork only the root at block 129, hash `0xe02bc89880aa8b1ae6b1be33b4b34d3b63496d70078a58d7c6d38f1e637ebea4`. Independent EVM simulation occurs at that block's timestamp 1792546129; the typed receipt signs that actual simulation timestamp and anchor. All final transactions use timestamp 1792546544. Full expiry checks execute again at settlement.

Transactions use impersonated public test accounts and synthetic balances, with receipt effective gas price zero. Gas units are measurements, not a fiat fee estimate. The three route receipts are alternative snapshot branches, not three simultaneous settlements on one canonical chain.

## Cost accounting

The original Foundry caller delta, 123,466,543 gas, remains preserved. An initial separate direct transaction used 125,369,240 gas. These measurements have different transaction-calldata, caller-memory/copy, and access-cost scopes. The matched transaction receipts are the comparison values.

Common prerequisites, excluded from per-finalization rows but included in lifecycle totals:

| Component | Gas |
| --- | ---: |
| Contracts, Google key and operator registry setup | 18,871,071 |
| Four actual model-certificate transports | 1,705,364 |
| Four full authenticated observations | 125,339,203 |
| Common prerequisite total | 145,915,638 |

Additional cache routes' setup:

| Component | Gas |
| --- | ---: |
| Cache deployment, nine chunks and seal | 48,116,567 |
| Relay deployment | 59,482,439 |
| Additional setup total | 107,599,006 |

The relay constructor includes an avoidable byte-by-byte copy of the 215,552 argument bytes. Its measured setup cost is reported, not hidden or claimed optimal. The finalizer consumes this exact evidence once, so this experiment cannot claim repeated settlement amortization of the packet.

The certified callback checks a prestate commitment before finalization, warming some consumer/gate/key/registry accesses. Its difference from direct execution is the complete route cost, including different pre-reads; it is not isolated signature-verification gas or evidence of reduced RSA/MIME computation.

## Security and interpretation limits

Every admitted source and model/request binding remains fixed. Full originals, DKIM signature and complete body, MIME selection, exact source set, rule/event identity, original signed-time/expiry, registry snapshot, input/token binding and all four request/email nullifiers remain checked by the unchanged finalizer. A failure must revert atomically without consuming part of the evidence.

The typed relay adds chain, code, packet, exact prestate, execution anchor, time and nonce bindings. These additional restrictions can reject a case the direct path would accept; the comparison is about safety and state effects, not identical liveness or identical revert selectors.

The inherited SDK still trusts its authorized quorum and permits arbitrary signed STORE updates. A typed callback does not remove that trust boundary. Local public test operators are not a production decentralized AVS. Google DKIM authenticates relayed bytes, not publisher truth; the historical key snapshot and prospective chronology limitations in the prior handoff remain. The case-specific credible-reporting fallback is not a general any-four-publishers policy.

## Reproduction and artifact boundaries

New implementation files:

- `contracts/src/judge/PeaceFinalizePacketCache.sol`
- `contracts/src/judge/PeaceFinalizeGasKillerRelay.sol`
- `app/scripts/laya-demo/peace_anvil_baseline.mjs`
- `app/scripts/laya-demo/peace_anvil_packet_setup.mjs`
- `app/scripts/laya-demo/peace_anvil_compare.mjs`

Private `frozen-comparison-plan.private.json` was saved before measurements. `protected-baseline-pins.private.json` protects 49 original artifacts. The baseline, packet setup, actor launch, independent worker execution, matched transactions, state comparisons and negative tests each have separate private receipts. Never publish raw email/MIME, private ABI fixtures or local actor directories.

The first baseline attempt stopped in client-side mixed-case address encoding before consumer deployment. The resume verified all seven successful setup transactions and resumed exactly at block 102 without reset, duplicate setup, or overwriting prior receipts. An actor build preflight also stopped on a renamed package's lock-file mismatch before actor execution. Failed preflight logs are retained; these are not successful actor runs.

## Completion results

All three real transactions succeeded and produced identical original consumer/gate state and outcome commitment `0x1d471043b19975aab91a1716396ac07850fb22a94c679cb2e5fd109e74de4b55`. Decision is Yes; source mask is 15; all four exact request nullifiers and all four email nullifiers are consumed. The original consumer's four model-certificate transitions remain unchanged. Relay nonce and SDK transition count differ as expected between routes.

| Route | Finalization transaction gas | Calldata bytes | Total including its setup and common prerequisites |
| --- | ---: | ---: | ---: |
| Uncached direct | 125,369,240 | 215,556 | 271,284,878 |
| Cached direct | 123,935,796 | 4 | 377,450,440 |
| Cached plus actual GasKiller certificate | 124,075,906 | 1,156 | 377,590,550 |

Caching reduces finalization by 1,433,444 gas (1.1434%). GasKiller adds 140,110 gas (0.1131%) compared with cached direct. Its 1.0316% reduction compared with uncached direct comes from the cache route, not eliminated authentication work. Including this prototype's actual cache/relay setup, both cache routes cost substantially more for this single settlement. This result does not demonstrate economically useful full-authentication acceleration.

Matched local transaction hashes:

- Uncached: `0x24e6b374efdd75a9ca41e855aae91fe29e4ad2fd9df3f76f3de1b5e3777e428d`.
- Cached direct: `0x0e099b3897bcc45a3bcbcdb1ebc014f40c6954099e59c77a944a74d92bae0a31`.
- Certified: `0x8b06085c0227a9fe9b17f3ae54f7f21fee2d2df1def4318d60566cbbc3a1a0ae`.

These are local synthetic snapshot branches. Saved receipt/block objects establish each execution even though the first two branches were reverted. No public explorer receipt is claimed.

Actual operator run: three commitments and three partial signatures, exit 0, 0.84365 seconds, one independently executed full-EVM call on each of the three worker RPCs. This excludes the earlier model-inference work common to all routes. Fixture SHA256 `4b4e3b5bd3b8cc0a224d9e55440c4995a2ad9e651bae48b69afe1947c31263b3`; compiled binary SHA256 `7121befe8ecab0541bacd411944ee17a184a7ec6bf32c3e8509271b6e88863b4`; launch manifest SHA256 `1822e422ab3bf8267544d2dda9b3f69345ea38703250f909858046ef7bd42d50`.

Root independently verified all 24 launch files, the compiled binary, all three independent receipt/RPC audit pairs, and all 12 generated actor files against the prepared upstream harness. It confirmed each operator made its own complete call at the anchor and obtained the same outcome. This supplements, rather than substitutes for, the actual SDK-accepted onchain certificate transaction.

Principal result files:

- `matched-comparison-results.private.json`, SHA256 `af2f7c0f7778df568e913d5b4ea45341b1b89b8f1aa9db069a1353ade27a2666`.
- `matched-*-transaction.private.json`, `matched-*-receipt.private.json`, and `matched-*-outcome.private.json`.
- `root-relay-actor-verification.private.json` and `gaskiller-relay-local/evidence/run-01.private.json`.
- `baseline-handoff.private.json`, `packet-setup-handoff.private.json`, and `cost-components.private.json`.
- `matched-final-state-dump.private.json`, with separate prestate dumps retained.

The final root regression passed **121 tests, 0 failed, 0 skipped**: the original 112 plus nine new fork-based equivalence/negative tests. Root session 30952 exited 0. `root-combined-121-tests.private.log` SHA256 is `c10015574e9204c0d22233d0f7d5714f8f93f6022866e30845d638e2ef57598c`.

New test file: `contracts/test/PeaceFinalizeGasKillerEquivalence.t.sol`, SHA256 `54f054bea735ffb7555fbf5a90533be82aaf63b4059fb5f5b3882e78cfe5a47b`. It pins the genuine actor fixture and exact already-accepted SDK transaction bytes. It checks matched positive outcomes and replay; original DKIM/receipt expiry; revoked Google key; operator-registry drift; corrupted cache shard; changed verifier code; wrong chain; altered certificate bytes; and signed-anchor age. Failed calls leave the decision unresolved and all request/email nullifiers unconsumed. One test demonstrates the intentional liveness difference: at block 387, the signed anchor is too old and certification rejects, while direct settlement remains valid at the unchanged timestamp.

The old documented 112-test matcher still excludes the separately named new suite. With a running local root at the pinned historical state, the combined command is:

```sh
cd /Users/wk/conductor/workspaces/means-of-prediction/newport-beach/contracts
LAYA_PEACE_GATE_FIXTURE=/Users/wk/.local/share/means-of-prediction/peace-demo-20261021/gate-fixture.private.json \
LAYA_PEACE_SCHNORR_FIXTURE=/Users/wk/.local/share/means-of-prediction/peace-demo-20261021/gaskiller-local/actor-fixture.private.json \
LAYA_PEACE_FOUR_GATE_FIXTURE=/Users/wk/.local/share/means-of-prediction/peace-four-report-demo-20261021/gate-fixture.private.json \
LAYA_PEACE_FOUR_SCHNORR_FIXTURE=/Users/wk/.local/share/means-of-prediction/peace-four-report-demo-20261021/gaskiller-local/actor-fixture.private.json \
LAYA_PEACE_RELAY_ACTOR_FIXTURE=/Users/wk/.local/share/means-of-prediction/peace-anvil-comparison-20261021/gaskiller-relay-local/actor-fixture.private.json \
LAYA_PEACE_RELAY_CERTIFIED_TRANSACTION=/Users/wk/.local/share/means-of-prediction/peace-anvil-comparison-20261021/matched-gaskiller-certified-transaction.private.json \
/Users/wk/.foundry/bin/forge test --match-contract '(PeaceBBC|PeaceFourReport|PeaceFinalize).*Test' --ffi -vv
```

Missing new fixtures fail explicitly. The 121-test result is a targeted suite, not a claim that a broad repository build or every unrelated test passes.

Preserved failed preflights are distinguished from this final pass. The first broad matcher saw all 112 old tests pass but accidentally included the newly appearing suite without its fixture variable; overall exit was 1. An early root negative run completed with five passes and one test-setup failure, `DKIM: not registrar`, because a getter consumed a one-call prank; it was fixed by evaluating arguments before the prank. Although root attempted Ctrl-C afterward, that run had already completed, so the provisional `root-progress-02.private.json` interruption interpretation is superseded by the saved log. Broad `forge build` also encountered a Yul error in a different test selection; the targeted new and combined suites compiled and passed. No production contract or frozen evidence was weakened to address these harness issues.

Final root audit rehashed all **49 protected original artifacts** unchanged and checked that the live root state still matched the certified transaction after the tests. Root and all three owned worker nodes were then stopped; all four local ports were confirmed closed. Receipts, pre/final-state dumps and private logs remain available. `root-final-protected-pins.private.json`, `root-final-live-state-check.private.json`, `cleanup.private.json` and `root-engineering-checkpoint.private.json` record completion. No commit, push, public deployment or GitHub comment was made.

The new runners intentionally refuse to overwrite prior artifacts. A fresh replay requires a new private output directory and regenerated context-bound actor fixture for its actual anchor. Do not assume a saved state dump restores block history or reuse this certificate against a different anchor; verify the node's header/state and rebuild the signed context as needed.


The remaining engineering question is how to reduce the authenticated full-body processing itself while retaining the desired trust boundary. This run establishes that adding a genuine certificate around unchanged verification does not do that. An optimized parser/cache design or a different verification mechanism would require its own frozen comparison; the prototype deployment-copy optimization is also separate from the measured finalization result.
