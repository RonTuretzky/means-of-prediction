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
training runs unpaced. The resume script now refuses to start on battery
and uses `caffeinate -i -s`; the machine must be plugged in with the lid
open (the screen may sleep).

### Student v2 epoch 1: results (September 24)

| yardstick | base Laya | student v1 | student v2 epoch 1 | Jev |
|---|---|---|---|---|
| vs Jev, 1,824 held-out units, question A positives (Jev fires 116) | | 67 | 110 | |
| vs Jev, question A agreement at 0.5 / Brier | | 0.972 / 0.012 | 0.970 / 0.017 | |
| human labels, 56 held-out facts: correct side | 22 | 33 | 33 | 49 |
| human labels: wrong side | 26 | 14 | 14 | 0 |
| sweep at 0.5: false fires on 25 true-No rows | 22 | 0 | 0 | 0 |
| sweep at 0.5: false fires on 37 weak/unlabeled rows | 36 | 2 | 2 | 2 |
| sweep at 0.5: true Yes found, of 3 | 2 | 2 | 3 | 3 |

The positive re-weighting closed the firing-rate gap to the teacher
(110 positives against Jev's 116, where v1 fired 67) without changing
the human-label picture: the student still settles the wrong side on 14
of 56 facts where Jev settles none wrong. False fires stay at Jev's
level. So distillation transfers Jev's caution but, so far, not its
side discrimination; the pick head agrees with Jev on 93% of held-out
units, a figure dominated by the "neither" majority. Epoch 2 continues
the same recipe; if it does not move the wrong-side count, the next
lever is the training mix (more positive units with both sides present,
or a side-contrast loss), not more epochs.

### Student v2 epoch 2, and where the wrong-side errors come from (September 24)

Epoch 2 finished at 16:15 (75 minutes at full speed): held-out soft
cross-entropy 0.2005, teacher-positive recall 193 of 298 (epoch 1: 211).
Against Jev on the held-out units it agrees more often (97.4% on
question A) but fires less (81 positives against Jev's 116; epoch 1
fired 110). On the human labels it is worse than epoch 1: 26 correct,
16 wrong side, 14 abstentions of 56 facts. **Epoch 1 is the v2 student
to keep.** The final `student-v2` directory holds the epoch-2 weights
with fitted temperatures; `student-v2/checkpoint_epoch1` is the one to
use.

The wrong-side errors are not side confusion in the model's reading.
On the 12 held-out facts that v1 and v2 epoch 1 both get wrong, the
student's own per-side probabilities favour the correct side every time
(for example pA 0.57 against pB 0.15) while its choice head picks the
other side. The choice head, trained on Jev's three-way pick
distribution and dominated by "neither", is the broken part; the
per-side heads carry most of what was distilled.

Reading the side from the per-side heads instead (pick the larger of
pA and pB when it clears a threshold, else abstain), with the threshold
chosen on the 524 training-market rows only, gives on the 206 held-out
rows:

| pick rule | 56 facts: correct / wrong / abstain | 45 positive controls: correct / wrong | false picks, 60 negative controls | false picks, 45 weak or unlabeled |
|---|---|---|---|---|
| v2 epoch 1, choice head | 33 / 14 / 9 | 36 / 8 | 1 | 0 |
| v2 epoch 1, side heads at 0.4 (chosen on training rows) | 34 / 2 / 20 | 42 / 1 | 1 | 0 |
| v2 epoch 1, side heads at 0.3 (chosen looking at held-out; not a clean claim) | 41 / 3 / 12 | 42 / 1 | 1 | 0 |
| v2 epoch 2, side heads at 0.35 (chosen on training rows) | 28 / 1 / 27 | 39 / 0 | 1 | 1 |
| v1, side heads at 0.3 (chosen on training rows) | 19 / 2 / 35 | 35 / 1 | 0 | 1 |
| Jev, choice head | 49 / 0 / 7 | 43 / 1 | 1 | 1 |

The clean claim is the second row: wrong-side settlements drop from 14
to 2 with no change in false fires, at the cost of abstaining on 20
facts instead of 9. The gap to Jev is now mostly recall (34 against
49), not safety. Next steps, in order: retrain with the choice
sequences dropped (`prepare --no-choice`) so the capacity goes to the
side heads; raise recall with more teacher-positive units rather than
more epochs (epoch 2 lowered recall); and pre-register the side
threshold from the training slice before any forward test.

### Student v3: student-proposed units, no choice head (armed September 24, evening)

Design, following the epoch-1 findings: (1) `laya_distill.py label-active`
lets the v2 epoch-1 student score every unlabelled own-market window of
training-split items plus entity-matched cross-market windows (16,000
candidates, cross ones ranked by entity hits), and sends the suggestive
ones to Jev (own-market windows at side probability 0.05 or more, first
claim; cross-market at 0.1; at most 6,000 units, about 30 cents). Every
email text that carries a validation case is excluded from candidates,
and the seed labels drop v2's 43 cross-market records drawn from such
texts; own-market records of twin emails are kept because the round's
market split admits shared bodies (validation-split.json's stated
limitation), and v1/v2 trained on them too. (2) `prepare --no-choice`
drops the choice sequences. (3) Two epochs from the v2 epoch-1 weights,
positive weight 6, no gradient checkpointing. (4) Each epoch checkpoint
is evaluated against Jev and against the human labels with
`laya_bench.py --side-threshold 0.4`, the threshold pre-registered on
training-market rows of v2 epoch 1.

Two adversarial review passes (three lenses, then a fix-verification
pass, each finding refuted or confirmed by two independent verifiers)
found 20 defects in the first drafts, all fixed before launch: chain
guards that would have accepted teacher error receipts as labels and
trained "v3" on no new data after a budget-exhausted day; a labelling
stage that re-scored and re-selected on relaunch; cross-market
candidates duplicating already-labelled window content; skip markers
written before their stage finished; the held-text leak above; a halt
rule that missed HTTP 402; a budget gate that looped forever on an
unlimited key. The stage now halts on the first non-retried 4xx or ten
consecutive failures, persists scores (keyed by student) and its
selection, dedupes by (window text, market), and the chain counts only
records with both an active source and a teacher answer.

Known limitation of every "held-out" number in this document: 85 of the
206 held-out rows (50 of 56 facts) share their full email text with a
training-split item of another market, per the round's split design.
The numbers are market-held-out, not text-held-out. A text-held-out
view (the 121 rows whose email text never appears in training) will be
reported alongside the v3 results.

Chain: `slides/laya-distill-v3.sh` (log `slides/laya-distill-v3.log`,
root `slides/laya-distill-jev-v3-20260924`); refuses to start on
battery and waits for teacher budget.

### v3 result (September 25): hard negatives alone collapse the student

The active stage ran at full speed overnight (the user left the lid open
and the screen dark): 26,594 candidates scored, 10,000 sent to Jev for
54 cents, no failures. Only 40 of the 10,000 were teacher positives (5
of the 2,708 remaining own-market windows, 35 cross-market): the entity
and quote heuristics that picked v2's windows had already found nearly
every window where a fact is reported. What the stage did find is 3,400
hard negatives, windows the student scores at 0.15 or higher where Jev
sees nothing settled, 188 of them above 0.4.

Training on all 10,000 would have made the set 96% negative, so
`prepare --active-min-score 0.15` keeps every teacher positive and only
the hard negatives, and the positive weight went to 10 to hold the
positive share of the loss at v2's level. Epoch 1 (22,034 sequences, 96
minutes) was still a regression: held-out soft cross-entropy 0.222
against 0.193 before training, teacher-positive recall 156 of 298
(v2 epoch 1: 211), question-A AUC against Jev 0.957 (0.990). On the
human-label benchmark the side heads went silent: median side
probability on the 50 held-out fact excerpts 0.17 (v2 epoch 1: 0.50),
maximum 0.33, so the pre-registered 0.4 threshold picked nothing.
Epoch 2 was stopped as pointless.

Why: of the 438 usable training positives, 407 are the short synthetic
control passages (median 260 characters) and only 31 are real
newsletter windows. The hard negatives are all real newsletter windows,
so the student learned "real newsletter text means nothing is settled",
which is the opposite of the job. The benchmark excerpts are real
newsletter passages.

### v3b (September 25): positives embedded in real newsletter text

`laya_distill.py label-augment`: every short positive is embedded four
times, whole, at a random position inside filler cut from
teacher-negative windows of real newsletters (filler subject used); each
of the 31 real positives is re-cropped four times around its located
evidence quote plus one contrast window that excludes the quote. Jev
labelled all 1,783 units for nine cents: 95% of embeddings positive on
the parent's side (1,540 of 1,628), 80% of crops positive, 0 of 31
contrast windows positive. Training positives go from 577 to about
2,200, most now surrounded by newsletter text. The student-proposed
negatives are dropped (`--active-min-score 1.01`, active positives
kept), choice sequences stay dropped, two epochs from the v2 epoch-1
weights at positive weight 2, evaluated per checkpoint with the same
pre-registered side threshold. Chain `slides/laya-distill-v3b.sh`, root
`slides/laya-distill-jev-v3b-20260925`.

### Keeping the GPU available while training (September 24)

`laya_distill.py train --gpu-share S` (also `MOP_GPU_SHARE=S` for the
evaluate stage and `laya_bench.py`) waits for queued GPU work after each
micro-batch and then sleeps in proportion to how long the step took, so
the trainer holds the GPU for about a share S of wall time. Five probes
of 6 to 8 updates each, GPU utilisation sampled every 0.28 s:

| setting | s/update | mean GPU util | idle share | longest busy burst | GPU memory |
|---|---|---|---|---|---|
| micro-batch 8, no pacing | 3.8 | 99% | 0% | continuous | 15 GB |
| micro-batch 8, share 0.5 | 6.9 | 63% | 27% | 3.1 s | 15 GB |
| micro-batch 2, share 0.5 | 8.3 | 66% | 31% | 1.4 s | 13 GB |
| micro-batch 2, share 0.3 | 13.8 | 41% | 59% | 1.4 s | 12 GB |
| micro-batch 8, no gradient checkpointing | 3.2 | 96% | 3% | continuous | 37 GB |

`--gpu-share auto` (env `MOP_GPU_SHARE=auto`) reads the seconds since
the last keyboard, mouse or trackpad event every two seconds: while
someone is using the machine it paces at `MOP_GPU_ACTIVE_SHARE` (0.3),
and once input has been idle for `MOP_GPU_IDLE_SECS` (180) it runs at
full speed; a returning user gets the paced GPU back within two seconds.
The log records each switch with the reason. A video watched without
touching the machine counts as idle.

Reading the GPU counter: `ioreg`'s "Device Utilization %" over-reports
fine-grained pacing. A synthetic 30% duty cycle reads about 73% when the
bursts are 60 ms (the benchmark's pattern) and about 45% when they are
one second (the trainer's pattern); the same 30% of work either way. To
know whether a paced job is what the counter is showing, stop it for a
few seconds (`kill -STOP`, then `kill -CONT`) and watch the counter fall.

The share knob buys responsiveness with wall time (0.5 is 2.2× slower,
0.3 is 3.6×). Micro-batch 2 keeps each busy burst short, which is what
the display compositor notices. Gradient checkpointing off is the fastest
unattended setting on this 128 GB machine. The resume script takes the
same choices as environment knobs: `GPU_SHARE`, `MICRO_BATCH`, `NO_CKPT`.

Night run, one command, unattended:

```sh
nohup /Users/wk/.local/share/means-of-prediction/slides/laya-distill-resume.sh \
  > /Users/wk/.local/share/means-of-prediction/slides/laya-distill-resume.log 2>&1 &
```

Launched September 24 at 11:56 local with `GPU_SHARE=auto NO_CKPT=1
MICRO_BATCH=2`: paced to 0.3 while the machine is in use, full speed
otherwise, no gradient checkpointing. The first presence switch to full
speed happened at 185 s of idle input, as designed. The lid was closed
at 12:38 during the epoch-1 benchmark and the laptop went into clamshell
sleep on AC power; no assertion prevents that without an external
display, so the chain froze (it ticks only during the 45-second
maintenance wakes every 15 minutes) until the lid is opened. The resume
script now holds `caffeinate -i -s` for the whole chain rather than only
the training stage; with that assertion in place from the start the
laptop stayed awake with the lid closed and the GPU kept working, so
the chain was relaunched at 14:39 without opening the lid.

The clamshell sleep also exposed a pacing bug: the pause is proportional
to the wall time of the last step, and a step that spanned an hour of
system sleep was charged as an hour of GPU time, so the benchmark slept
for two more hours after the machine woke. Charged busy time is now
capped at five seconds per step.

It evaluates epoch 1 on both yardsticks, resumes epoch 2 from the epoch-1
weights (`--init`, `--start-epoch 1`), evaluates epoch 2, and writes
one line per stage to the log. On a quiet, plugged-in machine the whole
chain is about two and a half hours unpaced. Artifacts land in
`slides/laya-benchmark-20260921/student-v2-epoch{1,2}` and
`slides/laya-distill-jev-20260922/eval-*.json`.

