# Fable round 1: autonomous prose-rule / local-Qwen improvement loop

Launched September 15, 2026. Private root:
`/Users/wk/.local/share/means-of-prediction/slides/fable-qwen-nyt-round1-20260915`.
Generator and teacher: Claude Fable 5.1 through the headless Claude Code
sign-in (`docs/FABLE-GENERATOR-TRANSPORT.md`). Judge: the unchanged pinned
local Qwen3.5-35B-A3B. The user authorized an unattended run of at least
twelve hours, including waiting for sign-in usage-limit resets.

## What is the same as the Astra round

The development inputs are byte-identical copies of the Astra round's frozen
files (18 files; hashes in `input-provenance.json`): the 1,915 semantic
development items and their seals, the 241 public inputs, cases, corpus,
controls, the runtime pin and the reservation markers. The baseline generator
and judge prompts are the Astra baseline text, byte for byte. Rule draws use
effort `medium`, teacher and optimizer calls effort `high`, as before. The
generator/teacher model is therefore the only changed variable in the
baseline arm.

## What is new

- **Root switch.** `MOP_QWEN_ROOT` redirects `qwen_round1.py` and every helper
  to the new root. Unset, all historical commands address the Astra root
  exactly as before. `q.FABLE_ROUND` gates the other changes below.
- **Hosted budgets.** Every hosted job carries a per-call dollar cap
  (`rule` 3, `feedback` 15, `optimizer` 60) bound into the frozen job hash.
- **Validation split.** `validation-split.json` was sealed before the first
  hosted call. Units are development groups (all markets of a factual
  market's group, with every control, weak and unlabeled row on them) or
  single markets; units are visited in SHA-256 order until the targets are
  met. Result: validation 56 factual / 420 controls / 32 weak / 47 unlabeled
  rows on 82 markets; train 105 / 1,100 / 59 / 96. Validation rows never
  enter a teacher shard; the optimizer packet still carries full-cohort
  aggregate summaries, and validation email bodies can appear in train rows
  of other markets. Both limitations are recorded in the split file.
- **Validation selection.** After each method, `fable_round.py
  validation-selection` scores validation rows only, applies the existing
  eligibility and paired-strict-improvement gates on that subset, and adds
  predeclared margins (at least +3 grounded factual passes and +8 strict
  positive passes on common validation rows, with false positives not above
  baseline). The leader is the allowed method with the highest validation
  utility, else baseline; the next revision chains from the leader, not the
  latest revision. Final `select()` intersects with the full-development
  gates and is not run by the loop.
- **Prompt review.** An automated lexical gate replaces the agent review:
  schema fields present, length caps, no market IDs, email IDs, fact keys or
  subjects from development data, no answer tables. Failure stops the loop.
- **Guarded draws for every method.** The bounded feeder now accepts
  `baseline`, `seed-*` and `v1`–`v9` in a Fable round and binds the Fable
  transport's hash into its plan.
- **Provider-aware audits.** `round4.verify_model_artifact` rebuilds the
  expected request with the transport named in the artifact;
  `qwen_capacity_recovery.usage_limited` recognises a Fable limit only when
  the transport could not wait it out.
- **Usage limits.** Under the `wait` policy the transport records the limit
  receipt, publishes a shared gate so concurrent workers pause, sleeps until
  the reset named in the receipt plus two minutes, and resubmits the same
  frozen request; every attempt is recorded. At most four waits and six
  hours per call. Only an unwaitable limit trips the persistent stop marker.

## Effort probe

Twelve unscored draws on six development public questions
(`slides/fable-effort-probe-20260915`):

| Effort | Completed | Median seconds | Median list cost | Median output tokens |
|---|---:|---:|---:|---:|
| low | 6/6 | 18 | $0.10 | 1,247 |
| medium | 6/6 | 30 | $0.13 | 2,185 |

`medium` was kept for rule draws, matching the Astra round.

## Driver

`fable_autorun.py` runs, per method: prompt review, guarded rule draws,
rule audit, judge preflight and token count, local judge (4 workers) in
parallel with train-only teacher feedback (3 workers, one attempt per
shard), audit, report, validation selection, then `optimize` for the next
revision from the leader. Phases run through the existing audited commands
with immutable driver markers; a completed phase is skipped on resume, an
uncertain one halts. Stop conditions: wall-clock projection past the
deadline before a judge pass, revision cap (3), two consecutive revisions not
allowed on validation, an unwaitable usage stop, a failed prompt review, an
incomplete rule cohort, judge failures above 1%, or any failed phase. It
never selects, freezes or opens fixtures. The stop marker is
`fable-loop-stopped.json`; progress is in `DRIVER-PROGRESS.json` and the
driver log outside the root.

```sh
cd app/scripts/research/blind
V=/Users/wk/.local/share/means-of-prediction/venv-research-py314/bin/python
export MOP_QWEN_ROOT=/Users/wk/.local/share/means-of-prediction/slides/fable-qwen-nyt-round1-20260915
export MOP_CLAUDE_CODE_BIN='/Users/wk/Library/Application Support/com.conductor.app/agent-binaries/claude/2.1.263/claude'
nohup caffeinate -i $V fable_autorun.py --methods baseline,v1,v2,v3 --wall-hours 12 \
  > /Users/wk/.local/share/means-of-prediction/slides/fable-qwen-nyt-round1-20260915.driver.log 2>&1 &
# monitoring
$V qwen_status.py | head -c 600; tail -3 "$MOP_QWEN_ROOT.driver.log"; ls $MOP_QWEN_ROOT/fable-loop-stopped.json $MOP_QWEN_ROOT/hosted-training-usage-stop.json 2>/dev/null
```

The Claude Code executable on PATH is 2.0.22 and lacks the headless flags;
the driver pins the 2.1.263 binary by hash in `protocol.json` and refuses to
start with any other.

## Results so far (September 16)

**Baseline, Fable generator with the pinned Qwen judge**, full 1,915-row
cohort, prompts byte-identical to the Astra baseline: grounded factual 65/161
(Astra 55), raw factual 89/161 (75), fact-family macro recall 0.434 (0.367),
timely grounded 6/19 (4), strict positive controls 509/608 (447), false
positives 15/912 (14), wrong-side positive controls 40 (28), unscorable 44
(160), utility 1.199 (0.972). Judge wall 2 h 19 min. Thirteen draws were
lost to a model-specific cap message ("reached your Fable limit", HTTP 429)
that the transport did not recognise as waitable; detection was widened
afterwards and those 42 rows stay unscorable in this method.

**Judge swap** (`fable_judge.py`, root `slides/fable-judge-baseline-20260915`):
Claude Fable 5.1 judged the same frozen baseline rules on a deterministic
730-row subset (all 161 factual, all 91 weak, 419 controls, 59 unlabeled).
Paired on the 693 rows both judges completed: grounded factual 149/160 vs
Qwen 65/160 (86 found only by Fable, 2 only by Qwen, 63 by both), raw
158/160 vs 89, macro recall 0.924 vs 0.434, strict positives 167/181 vs
152, false positives 0/237 vs 2, wrong-side 0 vs 12, settlement claims on
weak emails 0/63 vs 19, on unlabeled 0/52 vs 0, factual-outcome agreement
536/693. Fable judge: median 6 s per row, $123 list for 730 rows, 8 limit
waits. The judge, not the generator, is the binding constraint on this
cohort. Judge outputs from this arm do not enter teacher shards or selection.

