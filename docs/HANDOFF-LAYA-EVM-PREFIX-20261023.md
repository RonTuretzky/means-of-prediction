# Pinned LayA EVM embedding milestone

Completed October 23, 2026 UTC. The private artifact directory retains its
October 22 start date. This is a complete embedding-stage implementation for
the existing twelve Peace inputs, not complete LayA inference or settlement.

## Implemented and verified

`contracts/src/judge/laya/LayaQ16Embedding.sol` computes actual vocabulary-row
lookup and `LayaQ16LayerNorm.sol` computes the pinned `laya-int16-q16-v1`
normalization. The sparse input table contains complete 1024-element rows from
the original export. All tokens, including padding, are computed. Signed floor,
truncation, integer square root, gamma scaling and magnitude guards are explicit.
The older Q6 norm and Q24 operator experiments remain unchanged.

`app/scripts/laya-demo/peace_evm_embedding_fixture.py` checks model, runtime,
export, frozen-input and operator-receipt pins. It reconstructs each receipt's
numeric root to bind the saved embedding tensor to the original complete trace.
It replays only the embedding normalization and checks every scalar against the
saved tensor. The Solidity kernel receives real tokens and weights, not cached
answers. The test compares its complete computed output hash with the golden.

Validation: **17 passed, 0 failed, 0 skipped**, including all twelve BBC/CNN/ABC/RFI
q/A/B cases: **2,015,232 exact Q16 scalars**. Additional checks cover changed
real weights/token order, signed rounding, constant rows/bias, magnitude limits,
variance sums and malformed/missing rows. The 178 distinct vocabulary rows plus
gamma occupy 733,184 packed input bytes. The first run caught a misplaced
square-root recurrence; its failed log is retained. The corrected run took
9.23 seconds of serial test CPU time, excluding fixture generation/compilation.

Measured external kernel-call gas is 1,050,529,762–1,403,195,532 per full input.
This includes call/memory copying and excludes fixture parsing/setup. Foundry
uses an elevated gas limit and 1 GiB memory limit. These are operator-level
measurements, not production transaction feasibility or full-model savings.

All **70 protected baseline artifacts** still match the October 21 gas-profile
pin list. No relay/RSA gate, selected model, scores, frozen evidence, deployment
or baseline measurement was replaced. No full-model replay, training, browser
test, dependency download or new chain instance was run for this milestone.

## Pins and private evidence

- Model: `5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169`
- Runtime: `b06bce0d8250d8d3d6345278662feea160429cdf746ef26a5af1000489c54766`
- Export manifest: `b863c72eb531b7f86c67f23cf233067665e18b98f87a978eb2f6a4417e78b51d`
- Operator receipt: `db26d245a6da48b9e0693e4bf62ee6e5a6ddc698fb1a736241e880e0636c7c64`
- Reference: `/Users/wk/.local/share/means-of-prediction/peace-four-report-demo-20261021/`
- Export: `/Users/wk/.local/share/means-of-prediction/laya-chemistry-integer-20261021/export-v1/`
- Milestone: `/Users/wk/.local/share/means-of-prediction/peace-evm-prefix-20261022/`

The milestone directory contains `fixtures/fixture-manifest.private.json`,
all twelve input/hash fixtures, `weights.private.json`, the failed
`forge-embedding-01.private.log`, successful `forge-embedding-02.private.log`,
and `checkpoint.private.json`. Original mail and model artifacts remain private.

## Reproduce

From `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach`:

```sh
env OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 nice -n 10 \
  /Users/wk/.local/share/means-of-prediction/venv-laya-py312/bin/python \
  app/scripts/laya-demo/peace_evm_embedding_fixture.py \
  --output /Users/wk/.local/share/means-of-prediction/peace-evm-prefix-20261022/fixtures
cd contracts
env LAYA_Q16_EMBEDDING_FIXTURES=/Users/wk/.local/share/means-of-prediction/peace-evm-prefix-20261022/fixtures \
  nice -n 10 forge test --offline -j 1 --match-path test/LayaQ16Embedding.t.sol -vv
```

Without the private-fixture environment variable the real-data tests explicitly
skip; that is not a parity result. Fixtures cannot be regenerated with a different
model/runtime/reference without triggering pin failures. No paid calls are needed.

## Next bounded milestone and limitations

The first unsupported operation is layer 0's complete fused Q/K/V projection:
`Runtime.encoder_layer` calls `Runtime.mm` with
`encoder.layers.0.attn.Wqkv.weight` (3072 × 1024 int16 plus 3072 row shifts).
Implement its exact per-input-row quantization, signed nearest-ties-even,
int64 dot product and final floor shift, preserving the exported row shifts.
Compare the complete resulting tensor for each real padded input. Obtain new
intermediate reference taps without changing the pinned runtime or old receipts.
Keep the next run serial, low-priority and bounded; do not silently restart all
twelve full model forwards.

Production authentication/availability of the supplied sparse weight table is
still missing. The test verifies hashes offline; the kernel does not authenticate
weights against the original model commitment. QKV, RoPE, full attention,
remaining layers, heads, complete EVM inference and its Gas Killer integration
remain unfinished. Existing fixed Peace expiry makes this a retrospective
fixture. No on-chain or prospective settlement success is claimed.

The checkout includes unrelated modified and untracked research/demo work.
Only the two new libraries, their new test, fixture exporter and this handoff
belong to this milestone; do not blanket-stage the checkout.
