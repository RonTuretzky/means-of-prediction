# Blind Astra rules with local Qwen email judgments

For the September 13 checkpoint, current completed results, private artifact map,
and model-independent continuation instructions, start with
[QWEN-RESUME-HANDOFF.md](QWEN-RESUME-HANDOFF.md). Reviewed diagnostic source
snapshots are preserved in `research-checkpoint/`; their private inputs remain
outside Git.

This private research path runs alongside the regex experiments. Astra translates public market terms into plain English predicates; local Qwen3.5-35B-A3B evaluates one complete decoded email against the frozen predicates. It is prompt optimization, not weight fine-tuning. No experiment result authorizes a live settlement.

The generator receives only `marketId`, `question`, `rules`, `outcomeLabels` and optional public context. It cannot see the target email, market payout, expected answer, earlier judgments or score. Its JSON contains separate factual predicates, complete settlement predicates, abstention conditions and limitations. Qwen receives a complete semantic rendering of decoded HTML plus subject, DKIM domain and date metadata. It has no tools, browsing, other emails or expected answer.

The renderer retains all text outside script/style blocks, including preheaders and footers, paragraph/table boundaries, image descriptions and source attributes, accessible labels, and readable link destinations. Opaque NYT delivery routes use the original host plus stable references marked destination-unknown; every complete URL remains in a private sidecar. There is no snippet selection or length clipping. Existing cleaned `corpus.text` is excluded because it removed URLs and footer material. Full HTML remains immutable. This is a research representation, not an authenticated onchain rendering protocol.

A capability probe on the same longest email used 78,725 raw-HTML tokens in 357.55 seconds versus 14,969 semantic-body tokens in 14.95 seconds, with identical rule/system prompt. This is a runtime observation, not an accuracy comparison. An early HTML pilot's eight completed and four interrupted calls are preserved separately and excluded from prompt optimization and selection. The scored semantic baseline has its own sealed manifest and preflight.

Qwen returns independent `YES`/`NO` answers for each market outcome. `NO` means this email does not establish that predicate. Both `NO` and both `YES` leave the market unsettled. A separate factual-outcome diagnostic measures core claim recall without pretending that a reported fact establishes every original source, timing or finality condition. An exact body quotation is checked independently.

Each full development method includes:

- 241 public-only Astra rule generations.
- 161 previously labeled factual email/market pairs.
- 1,520 synthetic development controls covering 152 questions.
- 91 weak additional natural pairs, without invented gold labels.
- 143 deterministic full-email coverage diagnostics, which are unlabeled rather than assumed negative.

These make 1,915 scored rows per method. Failed Astra draws remain unavailable, so actual local requests can be fewer. Reports distinguish the 143-email manifest from attempted and completed unique bodies; the baseline's frozen rules permit 135 unique bodies to reach Qwen. Each raw result, complete original HTML, semantic body, public rule and score enters one audited feedback shard. Every shard's lessons enter the next optimizer, which can revise the reusable Astra generator prompt and Qwen judge prompt explicitly. At least two revisions are required, followed by useful improvements or a measured practical plateau, with at most six revisions before independent evaluation.

Feedback groups retain a 420,000-character serialized-group budget. If a complete email and its associated cases exceed that limit, only the case list is partitioned in deterministic case-ID order, repeating the complete HTML and semantic email in each fragment. Every case appears exactly once; repeated source bodies do not count as new independent emails. The first such failure and recovery are retained, all 55 previously completed shard inputs remain identical, and the optimizer receives the fragment lineage. A complete email plus even one case exceeding the bound fails explicitly instead of truncating evidence.

The frozen packets have a metadata limitation: 12 emails lack `signedDate`, affecting 28 rows (12 factual, four weak and 12 unlabeled). One email lacks subject/domain in 13 rows; a different email lacks receipt time in one row. Their complete bodies remain present. The other 131 dates come from parsed email `Date` / intake `proof.signedAt`, rather than DKIM's `t` signing timestamp. Missing metadata may affect source/time sufficiency. The scored inputs stay fixed. A separate prepared diagnostic restores only missing metadata, with exact raw-hash/header/intake linkage, and replays both original and restored packets after all fresh evaluation finishes. It cannot alter method selection.

The Qwen experiment has its own 12 unseen public questions and 120 separately authored sealed fixtures. Selection, model/runtime, judge prompt and 48 new Astra rule draws freeze before fixture labels are opened. The regex experiment proceeds independently. Old shared-holdout plans are retained as superseded artifacts, and the copied old holdout is excluded from this test.

The development controls cover forecasts, quoted or fabricated claims, wrong entities and events, timing boundaries and incomplete results. They do not provide a dedicated embedded-instruction or prompt-injection test. The judge's instruction to ignore email commands is a precaution, not evidence that injection resistance has been measured. The scored cohort stays fixed.

The reviewed v1 judge evaluates outer synthetic authoring wrappers as stipulated test scenarios while preserving every original predicate requirement. Substantive hypotheticals or repudiated claims inside a report remain non-evidence. This clarification is recorded separately from the preserved optimizer output. These are offline evaluation semantics; the wrapper assumption must not become a live-email authorization rule.

The final offline auditor binds answers to original HTTP bytes, recomputes scores, checks each actual input against its token preflight, and reports separate per-market and per-draw totals. It also verifies the recorded selection and rule freezes before reading fresh fixture material. Usage accounting includes failed attempts and teacher recoveries; missing usage remains unknown. Runtime probes, the interrupted HTML pilot and repeatability calls are counted separately from benchmark draws.

The current contract path has one affirmative predicate and a deadline-based negative resolution. It does not implement this research harness's two-outcome conflict checks or full-email Qwen judgment. A successful research output therefore does not establish that the deployed contracts can consume it.

Local inference uses the exact Qwen3.5-35B-A3B Q4_K_M GGUF artifact pinned by SHA256, with explicit LM Studio engine, context and request settings. The rendered template still opens a thinking tag despite the requested toggle; constrained JSON probes returned no separate reasoning content. The experiment does not claim that thinking was disabled. Quantized local inference does not constitute bit-exact onchain model execution. Local model loading, [structured output](https://lmstudio.ai/docs/developer/openai-compat/structured-output), and [runtime configuration](https://lmstudio.ai/docs/developer/rest/load) follow the LM Studio interfaces. The model source is [LM Studio's Qwen3.5-35B-A3B GGUF](https://huggingface.co/lmstudio-community/Qwen3.5-35B-A3B-GGUF).

The runner is `app/scripts/research/blind/qwen_round1.py`. All email material, model requests, labels, learned prompts and detailed reports live outside Git in `~/.local/share/means-of-prediction/slides/astra-qwen-nyt-round1-20260912`. Request errors are retained as unscorable; failed inference is never silently retried or counted as a safe rejection. Download transport recovery is recorded separately from inference.

Current results and precise runtime settings belong in the private `REPORT.md` and `runtime.json`; this document describes the protocol and does not claim a completed accuracy result.
