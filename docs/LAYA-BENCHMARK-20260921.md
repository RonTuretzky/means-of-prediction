# Typed-decision models as the settlement judge: Laya and Jev

September 21, 2026. [Laya](https://github.com/NandhaKishorM/laya) 0.3.5 is an
Apache-2.0, non-autoregressive typed-decision model: a 421M-parameter
ModernBERT encoder that answers `choice`, `score` and `noul` (calibrated
P(true)) questions in one forward pass, with no text generation. That shape
is attractive for a verifiable judge: deterministic, about eighty times
smaller than the 35B model the Gas Killer design re-executes, and about
21 ms per call on this Mac's GPU.

Tested with `app/scripts/research/blind/laya_bench.py` on the same 730 rows,
frozen rules and located passages used for the Qwen and Fable judge
comparisons (private root `slides/laya-benchmark-20260921`). Five trivial
sanity cases, including a forecast and a denial, were all answered correctly.

## Result: not usable out of the box

| Judge, same rows | Facts found | False claims |
|---|---:|---:|
| Claude Fable 5.1, whole email | 149 of 160 | 0 of 237 negative controls, 0 of 115 weak or unrelated |
| Qwen3.5-35B-A3B, whole email | 65 of 160 | 2 and 19 |
| Qwen3.5-35B-A3B, located passage, YES/NO per claim | 11 of 161 | 0 |
| **Laya `english`, located passage, choice of A / B / neither** | 56 of 161 right, **87 wrong side** | 6 of 237 and 26 of 150 |
| **Laya `english`, located passage, P(claim) ≥ 0.5** | 27 of 161, 17 wrong or conflicting | 3 of 237 and 9 of 150 |
| **Laya `typed-decisions`, located passage, choice** | 63 of 161 right, 76 wrong side | 5 of 237 and 22 of 150 |

The decisive test is the locator-free window sweep over whole emails on
yes/no markets, where a market-email fires if any 1,200-character window
clears the threshold (`english` checkpoint):

| Threshold on P(true) | Fires on true-YES facts (35) | Fires on true-NO facts (81) | Fires on weak or unrelated emails (134) | Fires on non-YES controls (238) |
|---:|---:|---:|---:|---:|
| 0.5 | 30 | 74 | 119 | 102 |
| 0.9 | 16 | 19 | 47 | 8 |
| 0.97 | 0 | 0 | 1 | 1 |

No threshold separates true from false. At 0.5 it fires on nearly every
newsletter that mentions the topic; at 0.9 recall halves while a third of
unrelated emails still fire; above that nothing fires. The
`typed-decisions` checkpoint never exceeds 0.9 on any row. The model scores
topical relatedness, not "this text reports the claim as a completed fact",
and on A-versus-B questions it picks the wrong side more often than the
right one, largely because most of our facts are "No" outcomes.

## What it is good for

Laya's own README says its base checkpoints sit below the majority-class
baseline on its typed-decisions benchmark and that all capability there
comes from fine-tuning; it ships the fine-tuning notebook. So the useful
reading is architectural: a small, deterministic, single-pass encoder is a
far cheaper thing to re-execute verifiably than a 35B LLM, and it is a
candidate **student** for the distillation step in
`docs/RESEARCH-PLAN-V2.md` (Track 2, experiment 5), trained on frontier
judgments over (passage, short criterion) pairs from dataset v2. As a
drop-in judge today it would settle markets wrongly.

Speed measured here: median 67 ms per call with four questions batched,
about 21 ms for one question, on Apple-silicon MPS; 11,584 forward passes
per checkpoint for the whole benchmark.

## Jev (TypeSafe), same benchmark, through OpenRouter

Jev is the closed, hosted decision model Laya compares itself to. It is not
in OpenRouter's model catalog; it is served at OpenRouter's alpha endpoint
`/api/alpha/decisions` with the same typed-question shape (`state`,
`questions` of type `noul` or `choice`), resolved here as
`typesafe/jev-1.13-20260917`. The key lives only in
`~/.config/means-of-prediction/openrouter.json`. The identical 11,584 calls
ran with eight in parallel: zero failures, median 319 ms per call, **$0.38
total**. Five sanity cases: 0.98, 0.01, 0.98, 0.01, 0.02.

| Judge, same rows | Facts found | Wrong side | False claims |
|---|---:|---:|---:|
| Claude Fable 5.1, whole email | 149 of 160 | 0 | 0 of 237 controls, 0 of 115 weak or unrelated |
| **Jev, located passage, choice of A / B / neither** | **137 of 161** | **0** | 6 of 237 and 2 of 150 |
| **Jev, located passage, P(claim) ≥ 0.5** | 97 of 161 | 0 | 5 of 237 and 1 of 150 |
| Qwen3.5-35B-A3B, whole email | 65 of 160 | 6 | 2 and 19 |
| Qwen3.5-35B-A3B, located passage, five-field | 45 of 160 | 2 | 0 |
| Laya `english`, located passage, choice | 56 of 161 | 87 | 6 and 26 |

Positive synthetic controls: Jev 172 of 182 by choice (Fable 167 of 181).

Locator-free window sweep on yes/no markets (a market-email fires if any
1,200-character window clears the threshold):

| Threshold | Jev: true-YES facts (35) | Jev: true-NO facts (81) | Jev: weak or unrelated (134) | Jev: non-YES controls (238) | Laya at the same threshold |
|---:|---:|---:|---:|---:|---|
| 0.5 | 32 | 1 | 6 | 15 | 30 / 74 / 119 / 102 |
| 0.7 | 27 | 1 | 6 | 6 | — |
| 0.9 | 9 | 1 | 4 | 0 | 16 / 19 / 47 / 8 |
| 0.97 | 0 | 0 | 0 | 0 | 0 / 0 / 1 / 1 |

### Reading

- **Jev reads like a judge, not a topic detector.** With the frontier
  locator's passage it recovers 85% of the facts with no wrong-side calls;
  with no locator at all it finds 91% of true-YES facts at a 0.5 threshold.
- **It is not clean enough to settle alone.** Six of 237 negative controls
  and, in the sweep, 6 of 134 unrelated emails and 15 of 238 non-YES
  controls fire at 0.5. Those are per-email rates; against a submitter who
  can try every email in a market's window they compound, so the two-outlet
  threshold and challenge delay in the plan are still required, and the
  per-market false-settlement rate still has to be measured.
- **It does not solve verifiability.** Jev is a closed hosted API: the chain
  would be trusting TypeSafe's say-so exactly as it would Anthropic's. Its
  value is elsewhere: a judge about four thousand times cheaper per call
  than the frontier model, fast, with probabilities to threshold on.
- **Where it fits:** the payout-and-timing consistency arm on the
  63,368-market pool becomes nearly free (10,000 judged pairs is roughly a
  third of a dollar instead of about $1,700); a second independent judge
  for disagreement rates; and a cheap teacher, alongside the frontier model,
  for distilling an open single-pass student such as Laya that the chain
  could re-execute.

