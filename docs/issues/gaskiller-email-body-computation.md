# Proposal: GasKiller-attested body parsing with compact onchain settlement

@tbsoc @nomoregas — requesting a concrete integration review for Means of Prediction. We want to authenticate long DKIM-signed newsletter bodies and evaluate a bounded text predicate without publishing/re-executing the entire body in the settlement transaction. Please confirm the ingress changes, supported deployment/security model, and proposed boundary below.

Companion: https://github.com/RonTuretzky/means-of-prediction/issues/1. This is a proposed adapter and benchmark, not a claim that the current GasKiller/LLM integration already solves body settlement.

## Problem and potential saving

Our exact-headline local test uses a 162,021-byte canonical NYT body and 15,059,245 settlement gas. Its direct ABI transaction exceeds common 128 KiB relay policy. Pagination makes transport possible but requires many data-deployment transactions and still executes the final full-body verifier/regex. The smaller 79,351-byte case consumed 8,685,448 gas.

GasKiller can potentially move deterministic body hashing, QP parsing, and regex evaluation into operator execution, returning a small attested result. The chain would receive signed headers, the RSA signature, commitments, and the attestation/result, rather than 162 KiB of body. No LLM is required to execute an exact regex. Savings and operator charges need measurement; no percentage is promised.

## Proposed hybrid boundary

1. **Pin the rule.** A new market mode commits to the source configuration, exact pattern, body parsing version, signed-date bounds, outcome semantics, and adapter address. Keep existing direct-proof markets unchanged. Existing deployed immutable markets need a new factory/implementation for this entrypoint.
2. **Keep RSA/header authentication onchain.** Refactor a reusable header-verification entrypoint to authenticate the publisher's RSA signature, unique From/Date/Subject, `d=`, key binding, canonicalization, and signed `bh=`; reject `l=`. Never accept a caller-supplied body hash without that verification. Verify active/pinned-key policy and market/source/date bounds again at finalization.
3. **Run the body predicate with GasKiller.** An `EmailBodyAttestor` SDK consumer exposes a tracked computation. Operators receive canonical body bytes and reproduce `sha256(body) == authenticated bh`, the v1 MIME/CTE policy, QP decoding, byte offsets, and exact regex. Execute expensive checks internally or through STATICCALL; do not emit an external CALL that re-runs the full verifier onchain. The computation writes only a bounded result/commitment and completion status. No email body in storage-update logs, CALL data, or persistent output slots.
4. **Bind every dimension.** Compute an application receipt key with unambiguous `abi.encode` over chain ID, market address, source index, rules/config hash, parser version, public-key hash, signed-header hash, DKIM signature/nullifier, authenticated body hash, witness offset/length, decoded-excerpt hash, and predicate/outcome. The attested output must match this key. The actual signed receipt/state diff must carry these commitments; a hash mentioned only in an offchain request is insufficient. This domain separation does not turn an operator attestation into a validity proof.
5. **Apply the small result.** Operators simulate at a pinned reference block/profile and sign the diff. A relayer submits `verifyAndUpdate` to the adapter. A separate market `submitAttestedBody` validates the compact receipt, performs the onchain RSA/header/source/rule/date checks, enforces unresolved/source/threshold/nullifier invariants, and reports payouts through the existing market logic. Do not make token balances or market payout storage writable by the SDK's general-purpose diff application. Use the adapter only for attestations.
6. **Handle changing state.** Finalization checks current resolution, source status, replay protection and the configured key-revocation policy. A stale operator result cannot override them. Pin deterministic computation inputs and verify the application receipt onchain; a historical simulation alone is not an authorization for present settlement.

This preserves cryptographic authentication of the signed headers and their body-hash commitment. **Whether the supplied body opens that hash and satisfies the predicate becomes operator-attested.** A dishonest quorum could assert a false predicate for a genuine signed email. Moving RSA itself offchain would widen that trust boundary and is a separate design choice, not required by this proposal.

## Current upstream blockers, checked 2026-09-10

- **Input cap is still present:** service commit `88a5763cb779986d807ab473c1b2b608efca990a`, `common/src/task_data.rs`, rejects `call_data.len() + storage_updates.len() > 128 * 1024`. The large email cannot pass that gate as a normal task even if the output is tiny. [Pinned validator](https://github.com/gas-killer/service/blob/88a5763cb779986d807ab473c1b2b608efca990a/common/src/task_data.rs#L38).
- **Required ingress change:** separate bounded operator-input size from onchain settlement-payload size. For this v1 workload, test at least a 256 KiB decoded input budget (196,608-byte body plus ABI/headers); account for JSON hex expansion, HTTP/proxy limits, task encoding, queue storage, signature protocols, resource budgets, and all validators. Alternatively add an authenticated, content-addressed body-upload/reference mechanism that every operator retrieves and hashes before execution. A URL without mandatory digest/availability validation is insufficient. Both approaches require service work; merely changing our RPC URL does not solve it.
- **Simulation/output distinction:** analyzer commit `f52709927199c7f0503dcc41b15663361489b679` documents a 2^40 gas simulation profile, while the applied payload must fit 2^24 gas. CALL operations re-execute onchain, and the unbounded extractor rejects CREATE/CREATE2. The body must disappear from the applied diff. [Pinned profile](https://github.com/gas-killer/gas-analyzer/blob/f52709927199c7f0503dcc41b15663361489b679/docs/UNBOUNDED_MODE.md).
- **Quorum is not a ZK validity proof:** SDK commit `e82dce3e4abc85962775b83fe7bab113a9e28038` verifies a signature over transition index, consumer, selector and storage updates, with BLS stake quorum checks. It does not re-execute the body calculation at settlement. Bind the input/rule commitments in the result and confirm deployment-specific signer, freshness and replay behavior. [Pinned SDK](https://github.com/gas-killer/solidity-sdk/blob/e82dce3e4abc85962775b83fe7bab113a9e28038/src/GasKillerSDK.sol#L68).
- **Slashing is not assumed:** [SDK #66](https://github.com/gas-killer/solidity-sdk/pull/66) and [service #345](https://github.com/gas-killer/service/pull/345) are still open/unmerged at this check. Please provide the actual supported deployment, checker/registry, operator membership/stake, admin powers, challenge/slashing contracts and verified runtime configuration. Website claims alone do not establish those properties for our deployment.
- **Availability and failure:** confirm access/API credentials, operator input retention and retrieval, timeout/retry behavior, and gas-profile provisioning. Test OOG/revert and require an explicit completed valid result; a transition-counter-only or partial diff must never become accepted body evidence. Offchain retention is necessary for independent replay/challenge when the body is omitted from chain data.

Our existing GasKiller path judges an authenticated **Subject**. It leaves DKIM verification onchain and does not yet implement this body adapter. LLM context budgets, natural-language rule evaluation and proof of email authenticity are separate concerns.

## Implementation and acceptance checklist

- [ ] Agree on the above trust boundary and deployed network/configuration with maintainers; pin reviewed SDK/service/analyzer revisions.
- [ ] Implement and validate large-input ingress independently of the bounded onchain payload.
- [ ] Build the isolated adapter plus compact header-authenticated market entrypoint and immutable rule/version commitments.
- [ ] Differential-test direct and attested execution on the same canonical bytes, including unsigned CTE, QP soft breaks, UTF-8, multipart rejection, duplicate tags, `l=`, offsets, wrong domain/key, invalid RSA and tampered bodies.
- [ ] Test wrong market/chain/rule/excerpt, stale keys/results, replay, fabricated or incomplete receipts, OOG, insufficient quorum, operator outage, unavailable input, and state changes between simulation and finalization.
- [ ] Public Sepolia E2E using only labelled synthetic emails: upload/task → quorum → compact settlement → trade payout/redemption → platform-fee withdrawal. Keep private mailbox data out of public issue/chain artifacts.
- [ ] Publish ingress bytes, final tx bytes, gas per stage and total, operator fees, latency, retry behavior, and amortized multi-market cost against direct/paginated baselines.
- [ ] Demonstrate direct/paginated fallback only for inputs that fit both that route's size and gas bounds; define timeout/abstention behavior for inputs without a feasible fallback.

## Review questions for @tbsoc and @nomoregas

1. Can the supported fleet accept a 256 KiB+ authenticated computation input with a small final diff, and where must the existing combined-size gate change?
2. Which signature/checker/slashing configuration is actually supported, and what is the intended input-commitment and data-availability mechanism?
3. Is a tracked body predicate with only a compact completion receipt the right integration shape? Can you help benchmark a 162 KiB synthetic newsletter and failure cases before we consider an LLM body judge?
