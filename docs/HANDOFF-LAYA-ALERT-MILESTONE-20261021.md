# Google Alerts Laya demo milestone — October 21, 2026

## Active scope and stop boundary

Continue the Google Alerts alert-student demo in this checkout. Do not switch to
inbox monitoring/cleanup or change any heartbeat/automation after compaction.
The bounded milestone is parser/binding tests, a pre-inference frozen calibrated
profile, and actual full alert-student reference inference. No newsletter work
or regression testing, research retraining, deployment/funds/wallet actions,
credential/security changes, or canceled issue #4 comment retry/replacement.

Source checkout: /Users/wk/conductor/workspaces/means-of-prediction/newport-beach.
Python: /Users/wk/.local/share/means-of-prediction/venv-laya-py312/bin/python.
Private artifacts: /Users/wk/.local/share/means-of-prediction/laya-alert-demo-20261021.

## Preserved state

Existing dirty app/scripts/research/blind/alerts_email.py and pre-existing
untracked Google Alerts slides/evidence files were preserved. The parser's current
bytes are pinned as input provenance. Common LayerNorm/matmul kernels remain.
Ten demo-created obsolete newsletter runners/tests were moved, with a hash
manifest, to /Users/wk/.local/share/means-of-prediction/laya-demo-20261021/abandoned-nyt-code/.
No existing tracked newsletter code was removed or tested.

## Frozen candidate and profile

Candidate review was written independently before inference:
laya-alert-demo-20261021/candidate-review.private.json.
Market 1395727, result index 3. The body result says Brewers clinched the NL
pennant and swept Dodgers in the NLCS; headline identifies October 15, 2026;
linked host mlb.com. Independently expected support is A true, B false.
The original complete rules and both predicates are frozen. No prompt selection,
predicate changes, or threshold tuning based on output.

Raw SHA256: 2d75c4968d136851825b44689fb7beddb270d36a148f3070e435236d05cc8f41.
The email was signed October 17 after recorded market closure October 16:
retrospective only. Stored DKIM verification is not fresh historical-key proof.

The final student-base root is selected because HANDOFF-ALERT-STUDENT-20261021.md
explicitly recommends it with fitted temperatures. Final and raw-epoch weights
are identical (421,293,830 stored tensor values, 1,685,197,088 bytes):
5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169.
Final noul:2 temperature: 1.1089085340499878.
Raw epoch noul:2 temperature: 1.983399510383606.
Threshold: 0.55, independently for A and B; q is diagnostic only.
The raw-epoch aggregate evaluation does not establish quality equivalence for
the final-root temperature. This remains an explicit attribution gate.

The original tokenizer metadata says TokenizersBackend. Stock Agent normally
rewrites it in place. The runner instead makes a private runtime copy and applies
that exact pinned compatibility function before freezing. Vocabulary/tokenizer
JSON, model weights, calibration and questions are unchanged. Both versions of
the metadata and all loaded files are pinned; original artifacts are unchanged.

Input uses the original alert_student.unit_state/questions path: whole-word cuts
110/162, publisher label with host fallback, q/A/B order, JSON subject-before-body.
Model subject is the extracted headline, never the email Subject/query.
Max sequence/head lengths are 320/160. Frozen lengths q/A/B: 174/173/168;
all state tokens retained.

Freeze SHA256: e00025dc7a6f133cc0fd8623236ea4d879f6a65daa8239cbd274df53d35bfb51.
Model manifest SHA256: 9d0153f9b6d7b940ba0e934b988ceeb695344ff9f233547e8a960b2394cdd13a.
Tokens SHA256: b0c9d648fd2d3cece4a6b68dfec153c59d8a69d7410dd5282c674ca8d77101c6.
Input SHA256: 2897171cfa8cc2e6d11287d878822a7a66b812d96d814fad14acdf4da135fe95.

## Completed bounded milestone

All commands below terminated. The bounded milestone is complete; the full demo
is not complete. Source changes remain uncommitted.

Final combined suite: **56 passed, 0 failed, 0 skipped**, exit 0:
23 adversarial MIME tests, 19 binding tests, 6 genuine Google Alerts body tests,
and 8 common LayerNorm tests, including the actual alert model activation.
Four fuzz tests ran 256 cases each. No newsletter tests were run.
Final log: laya-alert-demo-20261021/combined-alert-tests-corrected.log.

The first combined run exited 1 (46 pass / 10 fail) after the installed
forge 1.5.1 formatter removed braces from three one-line multi-statement blocks.
Those branches were restored with explicit multiline braces; an independent
source review found no additional control-flow loss. The corrected suite above
passed. The failed log is retained as combined-alert-tests.log.
Read-only forge fmt --check now exits 0. Avoid blind formatter writes, and
always rerun affected tests after formatting.
Remaining compiler warning: local variable shadowing in a synthetic test;
no unreachable-code warnings remain.

The freeze initially stopped at a tokenizer metadata guard (exit 1) before
inference or a frozen manifest. The separate compatibility copy resolved the
guard. Freeze process PID 72702 exited 0 and wrote all commitments before any
forward. Reference process PID 73004 exited 0.

## Actual reference output

CPU float32, four threads, q/A/B batch. All 28 ModernBERT encoder layers and
both decision-head layers executed. Stock replay with no hooks and the normal
head fast path matched exactly.

| Question | Returned probability | Threshold support |
|---|---:|---|
| A | 0.5846 | true |
| B | 0.0318 | false |
| q (diagnostic) | 0.4402 | not used |

The independently expected A-only flags matched. This is one selected
retrospective unit, not an accuracy estimate or prospective success rate.
Load time: 19.9452 seconds; full forward: 0.2261 seconds; stock replay: 0.2116 seconds.
Runtime measured on this host, not a gas estimate.

Post-run sensitivity only, applying the previously documented raw-epoch
temperature to the SAME captured logits: A=0.5476, B=0.1291, q=0.4664; both support
flags would be false. The selected final profile was unchanged and selected
before inference from the handoff. Thus the calibration attribution gap is
material, not merely bookkeeping; neither quality equivalence nor the older
raw-epoch performance figures can be claimed for this run.

Reference result SHA256:
69aa92e3ab306b4557e307d82587964ebd26e45845a4f21db3e7f3201d12a192.
Candidate review SHA256:
abf09ab822982ef419f38551401b170f9ab1f4f5843a9434394f4516ded9707c.

## Actual MIME witness and operator check

The private real MIME fixture has SHA256:
a2f14b64a38d04925c037c7595a16f4839f0b658d7e6345316c69304a2617816.
Complete canonical body is 154339 bytes, SHA256:
67b73056b8dbf54e2f8d20fe0fcba89413e3a7f1d93cef33d43dbbb0abef6676.
This matches the original signed bh=; the fixture export performed no fresh RSA
verification or DNS lookup and establishes no historical key proof.

The exact original QP window starts at 39529 and has 3398 encoded bytes (3172
decoded). It contains the Article opening, linked URL, complete headline,
publisher and complete description. The full balanced article row is 5172
encoded bytes / 4796 decoded, exceeds 4096, and is explicitly rejected.
No model input field was cropped to force this window. The omitted tail is
sharing/layout markup. Passing the byte witness does not implement semantic
article extraction or bind the model to that extraction onchain.

The genuine pure MIME parser external call consumed 113925661 gas in the
unbounded local Foundry environment. This is not ordinary-chain feasibility.
The actual width-1024 embedding LayerNorm fixture matches its integer reference;
maximum difference versus the captured float32 output is 0.000007. External-call
gas is 2606318. This isolated kernel does not establish full-model parity.
The retained matmul spike uses Q24 and LayerNorm Q6; the full arithmetic and
conversion policy still need definition.

## Source changes and commands

New active sources:
- contracts/src/lib/GoogleAlertBodyParser.sol
- contracts/test/GoogleAlertBodyParser.t.sol
- contracts/test/GoogleAlertRealBody.t.sol
- contracts/src/judge/LayaRequest.sol
- contracts/test/LayaRequest.t.sol
- app/scripts/laya-demo/artifacts.py
- app/scripts/laya-demo/alert_reference.py
- app/scripts/laya-demo/alert_mime_fixture.py
- app/scripts/laya-demo/calibration_sensitivity.py

Profile/binding/operator docs retain precise limitations. Existing common
LayerNorm/matmul sources/tests are preserved. The pre-existing alerts_email.py
diff remains 23 insertions / 1 deletion.

From the repository root, exact successful reference commands (both exit 0):

    /Users/wk/.local/share/means-of-prediction/venv-laya-py312/bin/python app/scripts/laya-demo/alert_reference.py freeze --candidate /Users/wk/.local/share/means-of-prediction/laya-alert-demo-20261021/candidate-review.private.json --out /Users/wk/.local/share/means-of-prediction/laya-alert-demo-20261021/reference
    /Users/wk/.local/share/means-of-prediction/venv-laya-py312/bin/python app/scripts/laya-demo/alert_reference.py run --out /Users/wk/.local/share/means-of-prediction/laya-alert-demo-20261021/reference --threads 4

Outputs are write-once. Do not rerun into this directory: use a new explicitly
named run directory and retain the old commitments. Do not change predicates or
select another candidate based on the output.

From contracts/, exact final combined test command (exit 0):

    LAYA_GOOGLE_ALERT_MIME_FIXTURE=/Users/wk/.local/share/means-of-prediction/laya-alert-demo-20261021/mime/fixture.private.json LAYA_REAL_LAYERNORM_FIXTURE=/Users/wk/.local/share/means-of-prediction/laya-alert-demo-20261021/reference/real-layernorm.private.json forge test --match-contract 'GoogleAlertBodyParserTest|GoogleAlertRealBodyTest|LayaRequestTest|LayaLayerNormTest' -vv

Read-only formatting check (exit 0):

    forge fmt --check src/lib/GoogleAlertBodyParser.sol test/GoogleAlertBodyParser.t.sol test/GoogleAlertRealBody.t.sol src/judge/LayaRequest.sol test/LayaRequest.t.sol

Python py_compile for all four new Python files and git diff --check both exit 0.
The private milestone-audit.private.json records hashes and command outcomes.

## Remaining gates and next executable step

1. Compose the existing RSA/header verifier with multipart v2. Implement a
   dedicated GoogleAlertEvidenceVerifier adapter: construct the header-only
   EmailProof internally (empty body/window fields) for DKIMVerifier.verify,
   while passing the original full proof to LayaRequest.validateEvidence.
   Require both on the same signed header/nullifier; pin Google signer/from,
   date/t/x/key provenance policy. Never accept a caller-selected parser fallback.
   Add a genuine fixture integration test using the saved signature/key material,
   plus tampered signature/body and mismatched-proof negatives. This is the next
   executable integration step, not completed by the pure MIME tests.
2. Build authenticated full-body article extraction and exact cropped input,
   including URL-host rules, markers, sequence masks, serialization, tokenizer
   and truncation. The current frozen Python reference is a reproducible
   baseline, not an authenticated onchain tokenizer.
3. Define complete deterministic integer arithmetic; export every encoder/head
   weight/operator and compare layer-by-layer against this fixed reference.
   Implement the missing complete ModernBERT/RoPE/full+sliding attention/GELU
   and decision-head path. Do not substitute Qwen RMSNorm/causal KV/SwiGLU.
4. Execute the full model through GasKiller, authenticate the request-bound
   certificate/result and shard state roots. Nonzero commitments or individual
   kernel results are insufficient.
5. Implement consumer source/date/conflict/timeout policy, challenge delay and
   settlement/redemption. Independent A/B support flags are not an exclusive
   outcome; this email was after market closure. Resolve the calibration
   quality-attribution gap before relying on claimed accuracy.

No transactions, deployment, training, mailbox actions, automation changes,
new credentials/security grants, or issue #4 comment writes occurred.
