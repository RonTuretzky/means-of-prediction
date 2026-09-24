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

### Seed student against the human labels (validation split only)

The 730-row benchmark overlaps the training rows, so only its 206
validation-split rows are a fair test (56 facts, 60 negative controls, 45
weak or unrelated emails, 3 true-YES and 25 true-NO yes/no facts in the
sweep):

| Held-out human-label view | Base Laya | Seed student | Jev |
|---|---:|---:|---:|
| Facts right by choice / 56 | 22 | 33 | 49 |
| Wrong side / 56 | 26 | 16 | 0 |
| False on negative controls / 60 | 1 | 1 | 1 |
| False on weak or unrelated / 45 | 10 | 4 | 1 |
| Sweep at 0.5: true-YES fired / 3 | 2 | 3 | 3 |
| Sweep at 0.5: true-NO falsely fired / 25 | 22 | 2 | 0 |
| Sweep at 0.5: weak or unrelated fired / 37 | 36 | 8 | 2 |

The seed student is about halfway from base Laya to Jev on correctness and
most of the way on false fires, after 366 labelled passages. Median 75 ms
per call with four batched questions on MPS.

## Full run, student v1 (September 22–23)

Labelling: 6,099 of 6,115 units answered by Jev for $0.30 after the key's
daily budget reset. Prepared 16,568 training and 6,462 held-out sequences.
Three epochs took 14.9 hours: updates slowed from 6.5 s to 27 s partway
through epoch 2 (variable-length batches on MPS), so v2 buckets batches by
length. Held-out soft cross-entropy against Jev: 1.11 before training,
0.22 / 0.18 / 0.19 after epochs 1 / 2 / 3.

| Held-out, 1,824 units | Base Laya | Student v1 |
|---|---:|---:|
| Claim A agreement / AUC / Brier | — | 0.972 / 0.993 / 0.012 |
| Claim B agreement / AUC / Brier | — | 0.959 / 0.978 / 0.019 |
| Market question (990 units) | — | 0.988 / 0.984 / 0.007 |
| Same pick as Jev | — | 0.939 |
| **Says yes where Jev says yes (298 pairs), at 0.5** | 196 | **168** |
| of which factual positives (110) | 47 | 34 |

| Held-out human-label view (206 rows) | Base Laya | Seed | Student v1 | Jev |
|---|---:|---:|---:|---:|
| Facts right by choice / 56 | 22 | 33 | 33 | 49 |
| Wrong side / 56 | 26 | 16 | 14 | 0 |
| False on negative controls / 60 | 1 | 1 | 1 | 1 |
| False on weak or unrelated / 45 | 10 | 4 | 0 | 1 |
| Sweep at 0.5: true-NO falsely fired / 25 | 22 | 2 | 0 | 0 |
| Sweep at 0.5: weak or unrelated fired / 37 | 36 | 8 | 2 | 2 |

Reading: the student reproduces Jev's safety almost exactly (false fires
now at Jev's level) and ranks positives well (AUC 0.98 to 0.99), but its
probabilities on true positives are pulled toward zero because about 94% of
training sequences are negatives: at 0.5 it recovers fewer teacher
positives than base Laya. This is an operating-point and class-balance
problem, not a capacity problem. Student v2 trains with teacher-positive
sequences weighted 6×, keeps every epoch's checkpoint with a held-out
positive-recall check, and buckets batches by length.

## Chain

`slides/laya-distill-chain.sh` waits for the key's daily budget, then runs
label → prepare → train (3 epochs) → evaluate → benchmark unattended, with
results in `slides/laya-distill-jev-20260922` and
`slides/laya-benchmark-20260921/student-v1`.

## Student v2, paused September 24

Epoch 1 (teacher positives weighted 6×, length-bucketed batches) finished
with held-out soft cross-entropy 0.203 and **teacher-positive recall 211 of
298** (v1: 168, base Laya: 196). Epoch 2 stopped at update 1,275 of 2,070.

What actually happened to the run, from the training log and the power
log (`pmset -g log`): the laptop was on battery the whole time. Whenever
the lid was open, updates took 3.5 to 5 seconds (an epoch is about 1.2
hours at that rate). The lid was closed three times (16:02, 19:30,
00:03 local) and each time the machine went into clamshell sleep;
`caffeinate -i` does not prevent lid sleep, so the run stalled for about
seven of its eleven and a half hours. Between 21:30 and 00:00 it ran at
10 to 18 seconds per update with the battery under 21%. The process died
at 03:09 with the battery at 3%, during a maintenance wake. Nothing was
wrong with the model or the code; the epoch-1 checkpoint is complete and
loadable. Its evaluations against Jev and the human labels were
interrupted and have not been written.

Cost of the job on this machine (M4 Max, 40 GPU cores, 128 GB), measured
with two 8-update probes on September 24: process memory 4.7 GB, GPU
memory in use 12 to 15 GB, about half a CPU core, and the GPU pinned at
97 to 99% while a step runs. Memory and CPU are not a concern; the GPU is
the shared resource, so anything the screen draws will feel choppy while
training runs. Micro-batch 2 with gradient accumulation 8 costs 15%
throughput (4.3 vs 3.7 seconds per update) and gives the window server
more gaps. The resume script now refuses to start on battery and uses
`caffeinate -i -s`; the machine must be plugged in with the lid open
(the screen may sleep).

Night run, one command, unattended:

```sh
nohup /Users/wk/.local/share/means-of-prediction/slides/laya-distill-resume.sh \
  > /Users/wk/.local/share/means-of-prediction/slides/laya-distill-resume.log 2>&1 &
```

It evaluates epoch 1 on both yardsticks, resumes epoch 2 from the epoch-1
weights (`--init`, `--start-epoch 1`), evaluates epoch 2, and writes
one line per stage to the log. On a quiet, plugged-in machine the whole
chain is about two and a half hours. Artifacts land in
`slides/laya-benchmark-20260921/student-v2-epoch{1,2}` and
`slides/laya-distill-jev-20260922/eval-*.json`.

