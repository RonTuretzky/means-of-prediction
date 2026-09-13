# V3 interruption and bounded continuation

Recorded September 13, 2026, after the continuation exited successfully. This is an offline research record. No deployment, weight training, live settlement, rule regeneration, or method promotion occurred.

V3 remains an **interrupted, incomplete original run**. A separately reviewed continuation completed only the 194 requests for which no original attempt directory or request existed. It did not retry the four requests that had started without a saved response. The cause of the original termination is unverified.

## Accounting and preservation

| Origin | Rows | Outcome |
|---|---:|---|
| Original finalized requests | 1,717 | 1,716 valid; one capped response |
| Original uncertain requests | 4 | Unscorable; never retried |
| Separately continued requests | 194 | All valid; one attempt each |
| Derived combined cohort | 1,915 | 1,910 valid; one failure; four unknown |

All 11,751 files in the original V3 rule, judgment, feedback, and driver trees retain their recorded hashes. The original completion, summary, and local-release markers remain absent. The combined accounting lives only in the continuation directory.

Seventy original teacher shards cover 1,675 cases. A further teacher shard covering 31 cases remains uncertain, and 209 cases were not included in an issued teacher shard. No hosted feedback was resumed by this continuation; its incomplete coverage must not be described as a completed V3 learning round.

## Procedure and verification

The runner is `app/scripts/research/blind/qwen_v3_unattempted_continuation.py`, with its focused tests and read-only `qwen_v3_continuation_runtime.mjs` helper. It used the pinned Python 3.14.6 executable, four local workers, the original V3 request bytes and full semantic email bodies, and the existing Qwen3.5-35B-A3B Q4_K_M instance. Temperature, seed, 2,048-token output allowance, schema, prompt, model bytes, engine, and context remained unchanged.

The run required exact plan/source/executable hashes, retired original process IDs, explicit external review, exclusive cooperative ownership, an idle queue, and four configured slots. It refused existing attempt directories, drained already running calls on an integrity stop, and never substituted a model or retried a request.

Validation passed:

- 17 focused runner tests and six supplementary runtime-audit tests, independently reviewed by the parent agent.
- All 241 public rule requests and raw Astra outputs reconciled.
- All 1,911 finalized local requests and raw responses reconciled, including status, model metadata, usage, and score reconstruction; every reported input-token count matched the complete input preflight.
- All 1,915 semantic packets reconstructed from the preserved complete HTML input. Every one of the 143 source emails has at least one successful judgment.
- Pre/post model artifact hashes, loaded-instance settings, LM Studio 0.4.1+1, engine 2.13.0, and SDK hash matched. The native API supplement checked context 131,072, evaluation batch 512, flash attention, eight experts, and GPU KV-cache offload.
- The continuation process exited zero. Local ownership was explicitly released after an idle/zero-queue check; no original V3 release marker was created.

The 194 new calls took 1,114.27 seconds of dispatch wall time, used 787,544 input and 22,620 output tokens, and summed to 4,452.88 request-seconds. Original finalized calls add 5,799,843 input tokens, 190,271 output tokens, and 28,707.13 request-seconds. The four unknown requests have unknown usage and duration; combined known totals are lower bounds. Interrupted scheduling and prefix caching prevent a clean latency comparison with uninterrupted methods.

## Derived development results

| Measure | V3 combined result |
|---|---:|
| Natural factual candidate hits | 68/161 |
| Natural factual hits with an exact quote | 51/161 |
| Grounded recall averaged across 33 fact families | 28.25% |
| Grounded hits in the closure-proxy stratum | 0/19 |
| Correct strict synthetic positives | 502/608 |
| False directional claims on negative controls | 54/909 scorable negatives |
| Wrong-side claims on positive controls | 49 |
| Unscorable controls | 4 |

On 143 factual pairs completed by both baseline and V3, grounded hits declined from 55 to 44. On 1,387 shared completed controls, correct positives rose from 446 to 462, negative false claims rose from 14 to 37, and wrong-side positives rose from 28 to 44. Across the full V3 control cohort, 103 of 605 raw directional claims disagree with the provisional strict control labels (17.02%). This is not a live settlement acceptance rate.

The natural labels are retrospective candidate labels, not adjudicated permission to settle. The closure date is a cached proxy, not verified resolution time. Synthetic factual-label agreement is also provisional: labels were authored for strict settlement, so administrative outcomes can differ from factual outcomes. Exact quotations establish textual presence, not entailment or source eligibility. These exposed, correlated development results do not support promoting V3.

## Related source review

A separate read-only review examined complete original terms, all six baseline rule fields, full email bodies, and raw-bound Qwen responses for one nomination, one tennis, and the CPI example in the 60-pair answerability panel. Both observed unsupported approvals retained their source conditions in the generated rule. The CPI example correctly abstained under its official-source restriction despite an old factual candidate label. The tennis generator also hardened a future confirmation contingency into a present prerequisite; that extra condition is not independently validated original-rule truth. This three-case diagnostic is not a prevalence estimate.

The user-approved real-data-first redesign remains in force. No V4, selection, reserved evaluation, or further local inference was started by this continuation. A separate source-check experiment is owned and reviewed independently; this document does not authorize or report its results.

## Private audit locations

Private study root: `~/.local/share/means-of-prediction/slides/astra-qwen-nyt-round1-20260912`. Continuation subdirectory: `v3-unattempted-continuation-v1`.

| Artifact | SHA-256 |
|---|---|
| `plan.private.json` | `b31badb41da3a242bbdc7f1458dd80cb7f69a306a9cf4a2481844f7184d08993` |
| `reviewed.json` | `d261e138b78145da0ca82da8a364718dcb89a177e2219e4f11dcb43a3b327411` |
| `derived-accounting.private.json` | `7ae55d371ee3574c6905efdc04375f5b1e9bedb7012c7c617ffd8da728d3eb49` |
| `post-run-audit-v1/audit.private.json` | `f82ddb4366acbf0bfba611779cb2e63ace6f270fdd5f18bde185461c92b93ac4` |
| `runtime-supplement-v1/post-dispatch.private.json` | `2920777d54c3e438710a57be62cc830941d111e979a343a9230106a9ce802878` |
| `local-ownership-released.private.json` | `b0c630c77068828ed0c13621f36f017c0444d60fff929be0d91c2597f1a76c9a` |

The study-root `real-answerability-baseline-source-review.private.json` has SHA-256 `eac53f3a146c51b2bdfcef9d7383ec3f502cc41f4b2ad965c0d2a8c5b04748c4`. It preserves the three source reviews and exact artifact lineage. Private artifacts contain emails and must remain outside Git. The recorded runner command has already completed and must not be rerun.
