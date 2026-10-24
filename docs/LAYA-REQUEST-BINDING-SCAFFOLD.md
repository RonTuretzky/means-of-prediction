# Laya alert request binding scaffold (2026-10-21)

The active demo uses a genuine Google Alerts result and the recommended final
alert-student base model. See [the exact profile](LAYA-ALERT-PROFILE-20261021.md).

Status: pure commitment/validation library and synthetic binding tests only. No
Laya runtime, authenticated result store, inference certificate or market settlement
is implemented here. Existing Qwen interfaces and market contracts are untouched.

`contracts/src/judge/LayaRequest.sol` binds chain/market context, rules/source policy,
source index, entire EmailProof, signature nullifier, complete canonical-body hash,
parser/extraction policy, byte window, decoded bytes, serialized input/token IDs,
model/tokenizer/schema/arithmetic/preprocessing/calibration/runtime pins, token
limit, support policy, threshold, expiry and nonce. Token IDs use
`keccak256(abi.encode(uint32[]))`.

The only active policy is `ALERT_STUDENT_BASE_SUPPORT_V1` (ID 3), fixed at 550000 ppm.
`supportFlags` returns A and B independently. Both can be true, including exact
ties and unequal scores. There is no exclusive candidate API or automatic
settlement mapping. Scores and execution roots remain unauthenticated.

Synthetic tests cover request fields/pins, versions, context, ranges, expiry,
independent A/B supports and ties, input/token mutations and body/excerpt/nullifier
binding. They show that commitment/body checks alone do not authenticate RSA.
`validateInput` checks equality, not canonical extraction or tokenization.

## Required consumer integration

1. Freeze real alert mail, market rules, selected result, source policy, final model
   and config, tokenizer, schema, parser, arithmetic and runtime before inference.
   Derive commitments from configured artifacts, not caller-supplied hashes alone.
2. Verify complete signed email material, full-body hash, date and signer. The
   alert binding requires GoogleAlertBodyParser v2's strict multipart profile and
   an encoded HTML-source window; no fallback to single-part v1 is permitted.
   Unsupported MIME/encoding fails closed. Google DKIM authenticates
   Google's result text, not the linked article's author or the event itself.
3. Extract an eligible result from authenticated body bytes. Apply the exact
   alert-student cuts, publisher fallback, question schema, serialization and
   tokenization. Bind extraction, markers, sequence boundaries, masks and truncation.
4. Authenticate actual deterministic Laya execution before storing results; bind
   request key, model/runtime/segment roots, masks, calibrated A/B outputs and
   arithmetic. Hash equality and a nonzero execution root are insufficient.
5. Recheck expiry and market state; atomically consume nonce/evidence identities
   and distinct article-host support. Several hosts in one Google email are not
   several newspaper DKIM senders. Duplicate units/hosts must not inflate K.
6. Define conflicts, missing evidence, date windows, challenge periods and timeout
   outcomes explicitly. Neither low A nor high B automatically establishes the
   existing market's NO resolution. Independent flags need a separately approved
   settlement policy before becoming an exclusive verdict.

From `contracts/`, run `forge test --match-contract LayaRequestTest -vv`.
