# Nobel Peace Prize Google Alerts demonstration

This is the active case selected by Ron on October 21, 2026, after preserving the Chemistry case. Worktree: `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach`. Private evidence: `/Users/wk/.local/share/means-of-prediction/peace-demo-20261021/`. No model, temperature, threshold, source text or original market rules were changed to obtain a positive result.

## Result and scope

The unchanged model supports **Yes** on the frozen BBC alert: float A/B support is **89.31% / 5.29%**. The complete deterministic integer model returns **89.32% / 5.29%**. Both produce A=true, B=false at the existing independent 55% thresholds. These are model support scores, not a measured probability that this market can safely be settled.

The original Google DKIM signature and full 20,461-byte canonical body verify against the saved Google RSA key at the verification clock. The Solidity evidence gate passes 22 tests; the actual Schnorr certificate/consumer suite passes 27 tests. All **49 contract tests pass, with no failures or skipped cases**. Three local operators independently execute the complete model and produce a genuine certificate; the real SDK/registry accepts it, and the consumer records A=true/B=false from the original authenticated email. This is a local observation result, not a production deployment or an original-market settlement receipt.

**The original market's source rule remains unsatisfied by this single BBC report.** The fixed consumer exposes a positive authenticated observation but must reject finalization with `SourceAdmissionMissing`. It has no constructor flag that reclassifies one BBC report as reporting consensus. Keep factual support, source admission, certificate verification and executed settlement as separate results.

## Market and precise evidence

- Market **5371292**: [Nobel Peace Prize 2026 awarded to an individual?](https://polymarket.com/event/nobel-peace-prize-2026-awarded-to-an-individual).
- Exact full rule text is preserved in `frozen.private.json`; SHA256 `f1ba951f9767de4eae4f2562b22bc4ad43db741fe3d30cecc5112a93eafece6d`.
- Yes requires at least one named individual laureate. A representative accepting an organization's prize does not count. Shared, declined and posthumous individual awards count. No also covers a withheld or unannounced prize at the stated year-end deadline.
- Primary source: the first official Norwegian Nobel Committee announcement at `nobelprize.org`. A consensus of credible reporting is an allowed fallback. This later BBC Audio profile is neither the first official announcement nor a consensus by itself.
- Frozen A: “At least one named individual was awarded the 2026 Nobel Peace Prize as a laureate.”
- Frozen B: “No named individual was a laureate of the 2026 Nobel Peace Prize.”
- Google Alerts result headline: **Profile | Navi Pillay - BBC Audio**. Publisher link: [BBC Audio](https://www.bbc.com/audio/play/m00331hm).
- Decisive text in the signed body: **“Navanetham 'Navi' Pillay has been awarded the Nobel Peace Prize for 2026.”** The same snippet identifies her as a South African jurist and former UN human-rights chief.

The alert query and email Subject are not settlement evidence. The model input's `subject` field holds the extracted article headline, not the owner-controlled Google Alerts query. No linked article text, article tail, NYT material or text from another result was substituted.

## Authentication and time

Original message SHA256: `8d6693baaf144f1366db221b970639e5f6028218f5dce91b492c17a4b49dc167`. Its private raw path is `~/.local/share/means-of-prediction/alerts-proof-monitor/raw/<SHA256>.eml`. Result unit is `531c9380501e31990f65ec0cda82026554eeaf10efaf960ca9cbbe574fe36a7c`, result index 0.

- DKIM: `d=google.com`, `s=20251104`, relaxed/relaxed, no body-length limit (`l=`).
- Signed time: **2026-10-18 02:58:28 UTC**. Signature expiry: **2026-10-25 02:58:28 UTC**. Signed `Date` agrees. These are signed timestamps; they are not an independent attestation of first receipt.
- Canonical body: **20,461 bytes**, SHA256 `ef09cd6700414ff97c243c6c7b564b457c19db3efdc26a0e84033bd033e939b4`.
- Canonical header SHA256: `21d51e434d69f0e402759041b46d92fc792cf4953425243169ee8bae3645fa43`.
- Exact original quoted-printable window: offset **8,078**, encoded length **1,265**, decoded length **1,169**. Full body hashing remains mandatory; this window does not replace the complete body.
- Saved 2048-bit RSA key snapshot: `~/.local/share/means-of-prediction/alerts-mail-20261006/dkim-dns.json`, snapshot time **2026-10-07 05:02:25 UTC**, file SHA256 `e1049166630ee8ed40b3ce69566c234417a8628cc08b57cc40c434d40d96c6a3`.

Current-clock and historical signed-clock verification against that saved key both pass. The gate fixture records **2026-10-21 01:16:48 UTC** as its current-time check; Foundry replays that saved fixture clock. A later rerun after expiry would be a historical test, not fresh current validity. This does not establish independently attested historical DNS, a live DNS lookup, publisher authorship or factual truth. The gate enforces the original DKIM expiry even though the separate model request expiry is later. Do not backdate an execution to pretend a previously expired message is currently admissible.

The saved market record was created **2026-10-06 09:07:16.032854 UTC** and was active/open in the October 6 snapshot. Its `endDate` is a rule deadline, not a verified closure time. Actual closure and independent first receipt are unknown. This is a retrospective replay, not a demonstrated pre-resolution production settlement.

## Frozen preprocessing and model execution

`peace_reference.py` and `peace_input_binding.py` preserve the complete original headline/snippet and the prior candidate's exact state, questions, token IDs, attention masks, marker positions/masks and question types. The reference performs one instrumented complete float forward and one separate stock parity replay. Both exactly reproduce the prior saved output. Extraction/quoted-printable/normalization checks: **42 passed**. Exact input/token/tensor binding and mutation checks: **20 passed**.

Input is **1,054 UTF-8 bytes**. Valid q/A/B token counts are **145 / 145 / 142**, combined commitment count **432**; the model batch pads each sequence to 145. Input commitment is keccak256 over exact input bytes. Token commitment is keccak256 over `abi.encode(uint32[] combinedIDs)`, not packed integers. Frozen input hash is `0x8a54831d5261500735ef336f3782e75cb7937e0f77eea0be8ce4746ac4850231`; token hash is `0x2dcfec0f907b4bf8a0c142f7bb81752e650a941b565399dbf87916269824da58`.

The immutable model has 28 encoder layers and two head layers, width 1,024, 16 attention heads, intermediate width 2,624, and 421,293,830 float values. Weights SHA256 is `5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169`. Profile SHA256 is `8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835`, temperature **1.1089085340499878**. q is diagnostic; A and B use independent support thresholds. Neither argmax nor a new confidence threshold replaces that policy.

| Question | Float support PPM | Integer support PPM | Support at 550,000 PPM |
| --- | ---: | ---: | --- |
| q | 882,800 | 882,900 | true (diagnostic) |
| A | 893,100 | 893,200 | true |
| B | 52,900 | 52,900 | false |

The existing model API rounds probabilities to four decimals before consumer PPM conversion. Integer receipts use their own actual outputs with that same rounding policy, not substituted float scores.

The exact Chemistry integer runtime and export are reused unchanged. Complete q/A/B ran three times for reproducibility; all outputs and all **99 emitted stage tensors** match exactly. Each bound replay checks all **337 export components**. Maximum unrounded YES probability error versus float is **0.0000691414**; maximum rounded error is **100 PPM** (0.01 percentage point). All threshold flags match. This is sample-specific numerical agreement, not a universal error bound: maximum raw-logit absolute error is 0.000628471; maximum layer absolute error is 45.15465, maximum layer mean absolute error 0.0944642, and maximum action-logit error 0.856369. The unused action head does not determine this A/B decision.

One BBC q/A/B replay takes about **31.6 CPU seconds** and performs **160,222,947,840 dense MACs** plus **3,875,328,000 attention MACs**. Full-model inference is CPU integer execution, not EVM inference or a ZK proof. Weight/LUT export is a separate one-time conversion; no float computation substitutes for layers in the integer forward.

## Implementation and important pins

New Peace files under `app/scripts/laya-demo/`:

- `peace_reference.py`, `peace_input_binding.py`: independently checked authenticated-window extraction and frozen model input.
- `peace_rsa_fixture.py`: genuine original full-body/RSA fixture with saved-key and time verification.
- `peace_gate_fixture.mjs`: ABI fixture and Peace-specific rules/source/parser/model pins.
- `peace_integer_receipt.py`, `peace_integer_parity.py`, `peace_integer_evidence.py`: original-freeze binding, operator output checks and numerical reports.

New contracts/tests: `PeaceBBCAlertEvidenceGate.sol` and `PeaceBBCSchnorrConsumer.sol`, under `contracts/src/judge/`, with corresponding tests in `contracts/test/`. Original Nobel and Chemistry code remains separate.

| Artifact | SHA256 |
| --- | --- |
| `frozen.private.json` | `b546ccf88a8d95b6f6a2183f249d60c0b7d764bd109235babae42cc19cf745d6` |
| `tokens.private.json` | `030b6e903ae96c335a963151335bc2f33bac31283ad964f7b86bd245716a84fe` |
| `tokens.bbc-integer-subset.private.json` | `84b94ae1cf97a3a6095ad4221da1e3dcef7463c91cf75d52a70fb474d0ff51f1` |
| `rsa-fixtures.private.json` | `5078c0d4ce818a126435020e9615937a57eded7fa232a2fe547f8f609f307cc9` |
| `gate-fixture.private.json` | `6fffae4d298c6fd4431a5828f99cad62ebb503d288da87bc64e3b2a24e99f030` |
| `reference-results.private.json` | `ce27df3191df85d1b881b8bd634250b4895c5af4a3e4ecaa4aefac0b8948423c` |
| `integer-evidence.private.json` | `8e1a1d867b6b2c6264e0f646760caff45635f2775c6f1dc2f5c1b4e4cd121303` |
| Unchanged `chemistry_integer_runtime.py` | `b06bce0d8250d8d3d6345278662feea160429cdf746ef26a5af1000489c54766` |
| Unchanged integer export `manifest.json` | `b863c72eb531b7f86c67f23cf233067665e18b98f87a978eb2f6a4417e78b51d` |
| New `peace_integer_receipt.py` | `fb5d1be08131c259a1046f40da8eb6c69a6b97a62918c671c4375fd6957c1086` |

Export location: `~/.local/share/means-of-prediction/laya-chemistry-integer-20261021/export-v1/`. Source execution root is `6c9a1ee7331522d9622f89caf72ec2ff5c869b2e6005ebe7fe418e01501d5d9a`.

The evidence gate independently authenticates the original header, checks the full body and window through the existing body-v2 path, and checks exact frozen input/token commitments. It does **not** implement arbitrary HTML extraction or tokenization in Solidity. Preprocessing is the separately checked deterministic offline computation. A hash commitment alone is not an execution proof.

## Real certificate and consumer integration

The separate private actor project is `peace-demo-20261021/gaskiller-local/`; its `RUNBOOK.private.md` contains exact reproduction commands and immutable launch provenance. The actual generated coordinator/participant/MuSig actor implementation and actual Schnorr SDK/registry are reused. Each of three participants independently runs the complete q/A/B runtime and checks its own 99 stage files and 337 export components before signing. Operators verify a proposed precommitted callback; they do not blindly copy the router's score.

The new local test consumer is `0x6354F0d8b4A45a30Af3D961A0153353a3a048590`, created from the public test deployer at nonce 2. Receipt version 2 has an explicit Peace context domain; selector `0x05d3b6e9`. It binds chain, consumer, market 5371292, request, input, tokens, model/profile, actual execution root, q/A/B scores, expiry and nonce. Bind this address **before** signing. Chemistry receipts and context must not be reused.

This is a local 3-of-3 agreement with public test scalars and in-memory transport. The registry is owner-managed with proof of possession and a 2-of-3 threshold. It is not independent organizational consensus, a live AVS or EigenLayer registration/slashing. The underlying SDK permits arbitrary quorum-signed storage patches; the typed consumer's second signature check does not protect it against a malicious authorized quorum signing arbitrary storage changes. The trust boundary remains explicit.

The actor process exited 0 after **34.008 seconds**. All three operators independently completed q/A/B: **nine fresh forwards**, **297 checked stage files**, and 337 checked export components per operator. All three emitted the same execution root and scores. This actor replay is separate from the three earlier reproducibility runs. Root independently rehashed the frozen inputs, actor fixture, binary, 26 launch files, each operator receipt and all 12 copied production actor source files; the source files match the prepared upstream harness.

The actual registry signature, certificate transport, full original email, input/token bindings and A-only observation passed together. Calling the actual consumer's `finalize()` returned `SourceAdmissionMissing`. Decision stayed `Unresolved`; no gate request or email nullifier was consumed. The 27 consumer cases include altered scores, execution root, model/profile, request, input, tokens, chain, consumer, market, protocol domain, signature, full body and time, plus replay, stake threshold and registry snapshot checks.

Measured local caller gas deltas:

| Operation | Gas |
| --- | ---: |
| Actual SDK certificate transport | 403,219 |
| Full BBC DKIM/body/input/token observation | 23,920,384 |
| Actual source-admission finalization rejection | 1,616 |

These include the local caller/copying context and are not a production transaction estimate or full-model EVM inference cost. Certificate verification reduces the model execution burden but does not remove full-email authentication costs.

Key completion receipts under the private base:

- `gaskiller-local/actor-fixture.private.json`, SHA256 `6cbcf08f1dd33039df672e7a33197606da4206d37628162ae6706b98d11f935b`.
- `gaskiller-local/evidence/final-actor-checkpoint.private.json`, SHA256 `c5e5dd9fa024034c7b1e4175e1b7d731b30338d5664854978e6eec95ff568ed1`.
- `root-artifact-verification.private.json`, SHA256 `05eb5f6d80dd680529dd184d42b7638d309aefb419cc58c233611f5152b653e2`.
- `integer-execution-audit.private.json`, SHA256 `1c4d4f793e24683f451a4b166b6024562b132fe3d52b2d71557cc5be23381fd1`.
- `evidence-gate-handoff.private.json` and `schnorr-consumer-handoff.private.json`: exact test commands, exit codes, logs and source pins. Final consumer handoff SHA256 is `f7743e9041be92df67a47610421e144b36955fa381c3ea5458619b1b185bc4af`.
- `integrated-observation-handoff.private.json`, SHA256 `73971c370263cb584c2d9950f46044d12779baa0d5684f32c9edb2d23f0bb869`: combined gate, actor and consumer receipt.

The actor uses config SHA256 `88a7b2b2a7519fc93159222bbd168d0484f32e1339a286c3e8d55a899c5c1792`, compiled binary SHA256 `b3f7df8fbd13d77f12407ea7c0ea9798960aa47a6c891b5dbaf15f6c612d0e49`, and launch-manifest SHA256 `61373eb4d244bda3adc30a4048ea753edc10cdac53cc184ff2e1012843c96e5f`. Its actual rebound request key is `0x254e64ec1215269533094ca69014f4ddb1774945f59693dc5c4acdadd24d9eb9`.

No actual wallet, funds, network deployment, transaction or browser acceptance was performed by this task. No commit/push was made; unrelated existing work and Chemistry artifacts remain intact.

Replay the existing local fixtures from the contracts directory (the environment variables contain file paths, not credentials):

```sh
cd /Users/wk/conductor/workspaces/means-of-prediction/newport-beach/contracts
LAYA_PEACE_GATE_FIXTURE=/Users/wk/.local/share/means-of-prediction/peace-demo-20261021/gate-fixture.private.json /Users/wk/.foundry/bin/forge test --match-contract PeaceBBCAlertEvidenceGateTest --ffi -vv
LAYA_PEACE_GATE_FIXTURE=/Users/wk/.local/share/means-of-prediction/peace-demo-20261021/gate-fixture.private.json LAYA_PEACE_SCHNORR_FIXTURE=/Users/wk/.local/share/means-of-prediction/peace-demo-20261021/gaskiller-local/actor-fixture.private.json /Users/wk/.foundry/bin/forge test --match-contract PeaceBBCSchnorrConsumerTest --ffi -vv
```

Without their genuine private fixtures these suites skip; a fixture-less run must not be reported as a positive authentication result. The completed runs above used the exact pinned originals and skipped no cases. The actor runbook explains fresh-directory replay; do not overwrite the completed operator directories or rewrite the frozen configuration.

## Source follow-up and continuation

The earlier Reuters/AP wires expired on October 17, before this BBC email was signed on October 18. There is no common DKIM-valid clock for that original three-message combination. A separately saved, model-score-independent inventory at `multi-source-candidate-inventory.private.json` examines existing corpus material for newer corroboration. Do not select a different input because it gives a preferred model score.

A later Reuters interview calls Pillay a Peace laureate, but its interview date alone does not establish the award year. Reuters Connect distribution must not be confused with Reuters editorial authorship: the DPA / PICTURE ALLIANCE caption explicitly associates Pillay with the 2026 prize but omits an award-status verb. A newer AP interview had a historical October 18–20 signature overlap with BBC, but is expired at review and its “last week” wording still needs publication context. Related-video/sidebar snippets must not be attributed to a different linked article.

The independent review read 15 occurrences covering 13 distinct exact snippets and rechecked three selected originals' raw hashes, full body hashes and extracted fields. It retained prior RSA metadata for those candidates and did not claim new RSA verification of every candidate. **No additional source was admitted or scored.** Full review: `independent-source-time-review.private.json`, SHA256 `a8f14264a51f65da383f9b3097244445370adb71789ac90896bb3153a11dd98c`. This is a focused corpus review, not proof that no admissible corroboration exists anywhere.

Any admissible addition needs its own source-policy review and pre-forward freeze. Do not modify the initial BBC freeze or silently turn its observation-only consumer into a settlement consumer.

To extend toward original-rule settlement, first admit the exact first official announcement or a defensible credible-reporting consensus under the unchanged rule, with consistent event/year and time provenance. Then freeze a new distinct request and test the new source policy. Missing evidence must not become No. Separately resolve retrospective acceptance, historical DNS/receipt attestation and production committee trust. Browser testing belongs to the coordinating parent task. Do not deploy, spend funds, substitute a model, tune thresholds, use NYT or post the canceled GitHub comment.

Chemistry is preserved in `docs/HANDOFF-CHEMISTRY-DEMO-20261021.md`: three genuine local certificates, all observations abstain, and actual finalization rejects with `InsufficientSupport`. Its 51 Solidity tests remain a useful real abstention case. Do not change that outcome to make the demonstration pass.
