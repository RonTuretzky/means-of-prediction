# Source-condition prompt diagnostic

September 13, 2026. This is a paired test on the already exposed, model-adjudicated
60-pair development pilot. It is not V4, weight fine-tuning, an independent test
set, or a change to either baseline. Its purpose is to locate and reduce Qwen's
unsupported settlement claims while preserving permitted reporting branches.

## Why this test

Review of saved baseline artifacts found that Astra retained the nomination
market's party-first-announcement or overwhelming-reporting-consensus route,
but Qwen claimed a settlement from one NYT result report. A tennis example also
retained its official-source or consensus route, yet Qwen claimed settlement
while listing unmet conditions. Exact factual quotation did not fix the source
problem. Separately, Astra hardened a future tennis confirmation fallback into
a present requirement; that generated-rule error must not be treated as original
market truth.

The reviewed CPI example preserved the BLS source and metric requirements and
correctly abstained. Its earlier factual-recovery miss is not a strict-settlement
error. These examples motivate an experiment, not a claim that all failure modes
have the same cause.

## Fixed procedure

Both variants receive identical frozen baseline Astra rules and complete semantic
emails. They retain the original two-message input, JSON schema, temperature 0,
seed 20260912, 2,048-token output cap and pinned local Qwen3.5-35B-A3B runtime.
The extra source-check paragraph is the only request difference. It distinguishes
exclusive official-source requirements, reporting consensus and an explicitly
permitted ordinary-reporting alternative. It warns against activating fallback
conditions before their trigger and keeps source, event, metric and time separate.

Use every one of the 60 pilot pairs, without selecting on either method's output.
Five frozen baseline rule generations are unavailable; preserve those failures
in each variant rather than generating replacements. This yields 120 accounted
rows and 110 local requests. Alternate which variant is queued first within a
pair. Four concurrent calls and shared model caching mean this is not a timing
benchmark or a guarantee of bitwise deterministic output. Alternating enqueue
order is not a serial crossover or a control for shared-prefix caching.

The runner preflights actual rendered input tokens with LM Studio's tokenizer.
It checks the loaded model artifact, application/SDK build, configuration, four
slots and empty queue before inference; configuration is checked again afterward.
Calls have one attempt, with immutable requests, raw replies, usage and terminal
status. Any interrupted/uncertain call requires reconciliation rather than an
automatic retry. No generation calls or reserved evaluation inputs are used.

## Scoring and interpretation

The existing adjudicated labels remain sealed. Score all 60 pairs and the common
completed subset, retaining unavailable rules, capped responses, other failures,
abstentions and unresolved labels. Report strict decisions and the separate
exact-quote filter. Compare supported recovery on the one answerable pair and
unsupported directional/conflicting claims on the 58 insufficient pairs.

One answerable event cannot establish positive-case accuracy. A model that
abstains everywhere can reduce unsupported claims without becoming useful.
Do not promote a procedure on this panel alone. Any promising result needs more
real, independently reviewed permitted-source positives and frozen evaluation.
Existing generated-rule defects are not repaired inside this prompt comparison.

Code: `app/scripts/research/blind/qwen_source_check_v1.py`.
Ten focused tests cover complete paired inputs, label exclusion, unavailable
rules, identity, order, raw-output integrity and capped-response classification.
The study's private artifacts contain the emails; they are not published.

Initial plan SHA-256:
`b6382073b45cdc071ac261d96ed6357d3450e807a2274b71d76e16760b42a686`.

A pre-launch audit amendment preserves the original draft source and plan,
pins the complete imported local source closure, and audits failed-response
metadata. All request bytes, inputs, labels and scoring decisions are unchanged.
The amended plan SHA-256 is
`0eef2547435c8ef2b2a27307c19cc215ad440661002f39345fb3821db9303c5f`.
The first audit amendment is also preserved; final review restored the explicit
requirement that completed responses identify the pinned model.

Read-only full-input preflight SHA-256:
`5c22c462a24bfedffcf8a7dcea9e2c3f8c9c43f654cc7ebc1236c3faa9c18137`.

Commands from the script directory:

```sh
python3 -m unittest test_qwen_source_check_v1 -v
python3 qwen_source_check_v1.py verify
```

Execution and two raw-response audits are complete. Do not rerun `run`: it is
write-once execution, not a resume command. Local inference ownership is released.


## Audited result

All 110 requests completed with valid structured outputs. The five unavailable
baseline rules remain five execution failures per variant; they were not replaced.
The same 55 completed pairs contain 53 insufficient-evidence cases, one answerable
case and one unresolved case.

| Measure on the 55 common completed pairs | Baseline replay | Source-check paragraph |
| --- | ---: | ---: |
| Directional/conflicting claims on 53 insufficient cases | 41 | 36 |
| Such claims surviving the exact-quote filter | 32 | 26 |
| Correct answers on the one answerable case | 1 | 1 |

Across the full 60-pair panel, the claim counts are unchanged, but the insufficient
case denominator is 58 and each method retains five unavailable-rule failures.
Neither denominator is population accuracy. One positive case cannot establish
conditional accuracy or positive-case nonregression.

The strict paired changes comprise eight withdrawn unsupported claims and three
new ones; 33 persist and nine pairs abstain in both variants. With exact quotes,
eight claims disappear and two appear. Two quoted withdrawals are only quote
formatting losses; both quoted additions repair formatting without correcting the
unsupported raw claim. Several abstentions still rely partly on hardened or
invented prerequisites. The new paragraph does not reliably enforce source rules.

The original historical baseline had 40 strict and 28 quoted claims on this pilot;
its replay has 41 and 32. Only 50/55 strict decisions and 28/55 complete canonical
JSON outputs agree across the old run and replay. Temperature zero and a fixed
seed did not make this concurrently executed procedure reproduce every answer.
The observed paired reduction therefore needs replication and more real positives;
it is not evidence to promote this prompt or revise the published baseline bars.

Input totals are 622,432 tokens for baseline replay and 636,732 for source-check
(+2.30%); output totals are 5,718 and 6,017. Summed request times overlap under
concurrency and are not wall-clock latency comparisons. This experiment did not
change model weights, generated rules, private labels, contracts or live markets.

Root raw audit SHA-256:
`11faa7c3a2feee5494fae2d0addb3bf2db9249ed0e33bd23fd4533788cb4a5fa`.
Independent reconstruction of all calls, unavailable rows, runtime, tokens and
scores: `1fdee2b8ba9a7036788c7df47b192b5c0df0c13a606f5f52e684188fe2602d99`.
Paired change review:
`309d962f638c0d47b48011406f0d8e905faaf7d4b7b20a2f85c183a3c62f64f9`.
