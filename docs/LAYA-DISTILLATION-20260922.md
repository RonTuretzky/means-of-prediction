# Distilling Jev into Laya for the settlement judge

Started September 22, 2026. Goal: an open, single-pass, deterministic judge
(Laya, 421M ModernBERT encoder, Apache-2.0) that answers "does this passage
report claim X as a completed fact?" the way the closed hosted Jev does,
because only an open model can be re-executed verifiably on-chain.

## Setup

- **Teacher.** TypeSafe Jev 1.13 through OpenRouter's `/api/alpha/decisions`
  (`typesafe/jev-1.13-20260917`), the same typed questions as the judge
  benchmark: three `noul` checks (claim A, claim B, the market question for
  yes/no markets) and one `choice` over A / B / neither. Key in
  `~/.config/means-of-prediction/openrouter.json`, never in the repo.
- **Units.** (window, market) pairs from the 1,915 development items:
  every item's own market on up to 12 windows of its email (1,200
  characters, stride 600; windows containing the frontier locator's quote
  or the question's entities first), plus 3 cross-market negatives per real
  email. 6,115 units: 4,291 train, 1,824 held out by the round's sealed
  market split, never trained on.
- **Training.** Laya's own recipe from its fine-tuning notebook (proper
  scoring reward with noise groups plus soft cross-entropy on the teacher's
  probabilities), single device on Apple-silicon MPS, gradient
  checkpointing, temperatures refit on train items only. About 2.5 s per
  micro-batch of 8 at 768 tokens.
- **Yardsticks.** Student vs teacher on held-out units (agreement, Brier,
  AUC); student vs the human-reviewed labels on the 730-row benchmark,
  restricted to the validation split (`heldout_view.py`).
- Code: `app/scripts/research/blind/laya_distill.py` (`label`, `prepare`,
  `train`, `evaluate`); benchmark `laya_bench.py --model-path`.

## Seed run (no new hosted calls)

The full labelling stalled on the key's one-dollar daily limit (its usage
had already reached two dollars before the run; no failed call was charged).
To prove the pipeline, the 366 located passages already labelled by Jev in
the September 21 benchmark were used as a seed: 1,001 training sequences,
365 held out, 2 epochs, 11 minutes.

| Held-out units, student vs Jev | Base Laya | Seed student |
|---|---:|---:|
| Claim A agreement at 0.5 / AUC / Brier | 0.70 / 0.65 / 0.14 | 0.80 / 0.88 / 0.06 |
| Claim B agreement at 0.5 / AUC / Brier | 0.60 / 0.67 / 0.17 | 0.67 / 0.77 / 0.13 |
| Market question (47 units, 4 teacher positives) | 0.72 / 0.76 / 0.18 | 1.00 / 1.00 / 0.02 |
| Same pick as Jev (A / B / neither) | 0.45 | 0.65 |

Held-out baselines on the benchmark's 56 validation facts, for the
human-label comparison that follows: Jev 49 correct by choice with 0 wrong
side; base Laya 22 with 26 wrong side; Fable whole-email 50 grounded; Qwen
whole-email 29.

## Full run

`slides/laya-distill-chain.sh` waits for the key's daily budget, then runs
label → prepare → train (3 epochs) → evaluate → benchmark unattended, with
results in `slides/laya-distill-jev-20260922` and
`slides/laya-benchmark-20260921/student-v1`.
