# Handoff: Laya settlement-judge student, distilled from Jev (state as of 2026-09-27 07:00 local)

> Start with `docs/HANDOFF-MASTER-20261004.md` for the premise, the history of the whole effort and what came after; this file is the detail for the Laya distillation.

One paragraph: we are training an open 421M typed-decision encoder (Laya) to do what
the closed hosted model Jev does for prediction-market settlement from newsletter
text: given a passage and a market's two factual statements, say which statement the
passage reports as a completed fact, or neither. The best student so far (v3c epoch 2)
settles 41 of 56 held-out facts correctly with 1 wrong side and zero false picks on
105 unsettled rows, at a threshold fixed in advance; Jev settles 48 with 0 wrong and 2
false picks. Everything below is on the MacBook Pro (M4 Max, 128 GB) under `/Users/wk`.

## Read these first

| what | path |
|---|---|
| Full narrative with every experiment, table and negative result | `docs/LAYA-DISTILLATION-20260922.md` |
| Laya and Jev benchmark write-up (before distillation) | `docs/LAYA-BENCHMARK-20260921.md` |
| Research plan v2 (why a verifiable open judge; forward test; admissible evidence) | `docs/RESEARCH-PLAN-V2.md`, deck `docs/research-plan-v2-deck.html` |
| Dataset v2 plan (more markets, more outlets) and the round that produced the benchmark | `docs/DATASET-V2-PLAN.md`, `docs/FABLE-ROUND-20260915.md` |
| Git: branch `RonTuretzky/replace-astra-with-fable-research`, last commit 95ee759 | repo worktree `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach` |

## Code (repo, `app/scripts/research/blind/`)

| file | role |
|---|---|
| `laya_distill.py` | the pipeline: `label` (Jev labels units), `label-active` (student-proposed units; hurt, kept for the record), `label-augment` (positives embedded in real-newsletter filler and re-cropped; this is what worked), `prepare` (sequences + soft targets; `--no-choice`, `--active-min-score`), `train` (`--positive-weight`, `--contrast-weight`, `--init`, `--start-epoch`, `--gpu-share`, `--no-grad-checkpoint`), `evaluate` (student vs Jev on held-out units) |
| `laya_bench.py` | benchmark on the 730-row human-labelled subset; `--model-path <checkpoint>`; `--side-threshold 0.4` derives the pick from the per-side heads (the choice head is broken, see write-up) |
| `heldout_view.py` | held-out (validation-split) view of any `rows.private.json` |
| `compare_students.py` | side-by-side of several rows files at several thresholds, plus the text-held-out view |
| `fable_transport.py`, `fable_judge.py`, `qwen_round1.py`, `fable_round.py`, `fable_autorun.py` | the earlier generator/judge round (Fable and Qwen); not needed for the student work |

Environments: Laya/torch in `/Users/wk/.local/share/means-of-prediction/venv-laya-py312/bin/python`
(all Laya scripts); the research venv `.../venv-research-py314/bin/python` cannot run torch.
Teacher key: `/Users/wk/.config/means-of-prediction/openrouter.json` (`{"apiKey": ...}`, mode 0600;
$1/day limit; ~$0.00005 per Jev call; it was pasted in chat once, so rotate it). Never commit it or
any `*.private.*` file.

## Data and artifacts (private, `/Users/wk/.local/share/means-of-prediction/slides/`)

| path | contents |
|---|---|
| `fable-qwen-nyt-round1-20260915/` | the round: `development-items-semantic.private.json` (1,915 items, emails + labels), `public-inputs.json` (markets), `methods/baseline/rules.json` (factual A/B statements per market), `validation-split.json` (sealed held-out markets/cases; note its `limitation`: bodies are shared across markets) |
| `fable-judge-baseline-20260915/judgments.private.json` | located evidence quotes per case (used for excerpts and crops) |
| `jev-benchmark-20260921/jev-1.13/rows.private.json` | Jev on the 730-row subset (the teacher's own benchmark) |
| `laya-benchmark-20260921/student-*/rows.private.json` | every student's benchmark rows: `student-v1`, `student-v2-epoch{1,2}`, `student-v3-epoch1`, `student-v3b-epoch{1,2}`, `student-v3c-epoch{1,2}`; `english/` is base Laya |
| `laya-distill-jev-20260922/` | v1/v2 root: `labels.private.jsonl` (6,099 Jev labels + old error receipts), `student-v2/checkpoint_epoch1` (the v2 baseline student) |
| `laya-distill-jev-v3-20260924/` | v3 root: v2 labels + 10,000 student-proposed units (`active-scores.private.jsonl`, `active-chosen.private.json`); `student-v3/checkpoint_epoch1` (worse; keep for the record) |
| `laya-distill-jev-v3b-20260925/` | **current root**: `labels.private.jsonl` (15,936 + 1,783 augmented = all labels), `augment-chosen.private.json`, `prepare.json`, `train_items.pt` (16,927 seqs), `validation_items.pt` (4,638), `eval-*.json` (student vs Jev), `student-v3b/`, **`student-v3c/checkpoint_epoch2` = best student** (1.6 GB; `student-v3c/` itself is the same weights with fitted temperatures) |
| `laya-distill-jev-v3b-20260925.*.log`, `laya-distill-jev-v3-20260924.*.log`, `laya-distill-jev-20260922.*.log` | per-stage logs next to each root |
| `laya-distill-v3c.sh`, `laya-distill-v3b.sh`, `laya-distill-v3.sh`, `laya-distill-resume.sh`, `laya-distill-chain.sh` | chain scripts (one line per stage into `laya-distill-*.log`; every stage skipped if its last artifact exists; refuse on battery; hold `caffeinate -i -s` for the whole chain) |

## Use the best student

```sh
V=/Users/wk/.local/share/means-of-prediction/venv-laya-py312/bin/python
CK=/Users/wk/.local/share/means-of-prediction/slides/laya-distill-jev-v3b-20260925/student-v3c/checkpoint_epoch2
cd /Users/wk/conductor/workspaces/means-of-prediction/newport-beach/app/scripts/research/blind
$V laya_bench.py --backend laya --model-path $CK --side-threshold 0.4 --root /tmp/some-dir   # ~15 min at full speed
$V heldout_view.py /tmp/some-dir/rows.private.json
$V compare_students.py --labels .../laya-distill-jev-v3b-20260925/labels.private.jsonl best=/tmp/some-dir/rows.private.json
```
In code: `laya.Agent(CK, device='mps').predict(state, questions)` with the questions built by
`laya_distill.questions_for(public_market, rule)`; take `A` and `B` `noul` probabilities, pick the
larger if it is at least 0.4, else abstain. Ignore the `pick` (choice) answer.

## Reproduce or continue training

Retrain v3c from scratch (data already prepared, ~3 h + 45 min of evaluation):
```sh
GPU_SHARE=auto MICRO_BATCH=8 EPOCHS=2 POSITIVE_WEIGHT=2 CONTRAST_WEIGHT=4 \
  nohup /Users/wk/.local/share/means-of-prediction/slides/laya-distill-v3c.sh \
  > /Users/wk/.local/share/means-of-prediction/slides/laya-distill-v3c.log 2>&1 &
```
(Delete or rename `student-v3c/` first; the chain skips finished epochs.) Knobs: `GPU_SHARE=1`
for full speed, `auto` yields the GPU while someone is using the machine; `NO_CKPT=1` (default)
skips gradient checkpointing (37 GB, 16% faster). Machine rules learned the hard way: plug in
(chains refuse on battery), keep the lid open (a closed lid with no sleep assertion sleeps; with
the chain's assertion it stays awake but runs hot), and read the GPU counter with the caveats in
the write-up.

## What we learned (short)

1. The choice head is broken; the per-side heads carry the judgement. Pick from `pA`/`pB` at a
   threshold pre-registered on training-market rows (0.4). This alone took wrong sides 14 to 2.
2. Only 31 real newsletter positives exist in training; 407 positives are short synthetic
   passages. Embedding those passages in real newsletter filler (Jev re-labels them, 95% stay
   positive) fixed the teacher fit.
3. Student-proposed hard negatives alone make the student silent on real newsletter text (v3).
4. Weighting the other side's negative sequence on every positive unit (`--contrast-weight 4`)
   removed the A/B confusion: wrong sides 5 to 1, false picks 2 to 0 (v3b to v3c, same data).
5. Held-out numbers are market-held-out, not text-held-out: 50 of the 56 facts sit in emails
   that also appear in training under other markets. Only a forward test on fresh newsletters
   settles the real gap to Jev.

## Open items

- Rotate the OpenRouter key.
- Dataset v2 needs the newsletter mailbox subscriptions and the Guardian/NYT API keys (see
  `docs/DATASET-V2-PLAN.md`); more real positives is the one lever left for recall.
- Forward test protocol in `docs/RESEARCH-PLAN-V2.md`; use threshold 0.4 and the v3c epoch-2
  checkpoint, pre-registered.
- Memory note for the assistant: `~/.claude/projects/-Users-wk-conductor-repos-means-of-prediction/memory/laya-jev-distillation.md`.
