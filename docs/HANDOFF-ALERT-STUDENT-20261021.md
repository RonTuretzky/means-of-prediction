# Handoff: alert-shaped Laya student, results (October 21, 2026)

Short results handoff for the alert-shaped student. Context, history and design decisions are in
`/Users/wk/conductor/workspaces/means-of-prediction/newport-beach/docs/HANDOFF-MASTER-20261004.md`
(section 5, item 4). Every path below was checked to exist on October 21. Nothing is running.

## What was trained

Laya (421M ModernBERT encoder) distilled from Jev (jev-1.13.0) to answer "does this alert result
state the market's A (or B) predicate as a completed fact?". The inputs are the units Google Alerts
carries: a headline cut to 110 characters, the publisher, and a snippet cut to 162 characters.

- Data: 520,552 Jev labels on the GDELT alert-shaped corpus. 38,408 positive and near-miss units
  were relabelled by Jev on the cut text. 144,904 training sequences (A/B only); 103,272 clean
  held-out units.
- Split: sealed by event group (12% of groups), plus the probe groups, plus all markets closed from
  August 17. Shared text and post-cutoff units are kept out of training. The threshold is chosen
  on a 4,000-unit calibration slice that is never trained on.
- **student v1**: from the v3c epoch-2 weights, 2 epochs, micro-batch 32, positive weight 2,
  contrast weight 4. Finished October 19 (91.6 hours of wall time, with sleeps and battery pauses).
- **student base**: from the untuned Laya weights, 1 epoch, same settings. Finished October 20
  (3.2 hours).

## Results

Both students calibrate to threshold **0.55**. Their probabilities are compressed (no unit above
0.81), so Jev's 0.7 does not carry over.

Held-out units (103,272):

| model | A agreement at 0.5 | A AUC vs Jev | A recall at 0.5 | A false fire at 0.5 |
|---|---|---|---|---|
| v1 epoch 1 | 98.92% | 0.9911 | 0.614 | 0.49% |
| v1 epoch 2 | 98.98% | 0.9913 | 0.667 | 0.50% |
| base epoch 1 | 98.95% | 0.9910 | 0.612 | 0.45% |

Per market on the held-out markets (1,381 YES and 2,263 NO; units dated on or before close; any
host):

| reader | t | K = 1 coverage / false YES | K = 2 | K = 3 |
|---|---|---|---|---|
| Jev | 0.7 | 6.5% / 3 (0.13%) | 4.0% / 2 | 2.8% / 2 |
| v1 epoch 2 | 0.55 | 6.8% / 8 (0.35%) | 4.2% / 2 | 2.8% / 0 |
| base | 0.55 | 6.5% / 4 (0.18%) | 4.1% / 2 | 3.0% / 0 |

Real alerts (the forward run: 7,635 pairs, 60 open markets, none had happened): no YES claim on any
market at 0.5, 0.55 or 0.7 for either student. B claims on 2 markets at 0.55 and none at 0.7.

Reading:
- At K ≥ 2 both students match Jev market for market.
- At K = 1, v1's 8 false YES are 3 cases shared with Jev (Love Island, the US strike on Nigeria, the
  Russian strike on Poland) and 5 sibling or outcome-bucket confusions, each from a single host.
- Starting from v3c bought nothing at the market level. **Recommended checkpoint: student base**:
  the same coverage, fewer single-host false YES, and a third of the cost.
- Low coverage is the GDELT outlet mix, not the reader.

## Paths

Models (each loads with `laya.Agent(<dir>)`; run with
`/Users/wk/.local/share/means-of-prediction/venv-laya-py312/bin/python`):
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/student-base`
  (recommended; final weights plus fitted temperatures). Raw epoch:
  `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/student-base/checkpoint_epoch1`
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/student-v1`
  (final, equal to epoch 2 plus temperatures). Raw epochs:
  `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/student-v1/checkpoint_epoch1` and
  `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/student-v1/checkpoint_epoch2`
- Initial weights of v1:
  `/Users/wk/.local/share/means-of-prediction/slides/laya-distill-jev-v3b-20260925/student-v3c/checkpoint_epoch2`

Evaluations (threshold, calibration, held-out by split, forward real alerts):
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/eval-student-base-checkpoint_epoch1.json`
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/eval-student-v1-checkpoint_epoch1.json`
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/eval-student-v1-checkpoint_epoch2.json`

Per-unit student labels (private; readable by `alerts_tables.py --labels`):
- held-out: `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/student-labels-heldout-student-{base-checkpoint_epoch1,v1-checkpoint_epoch1,v1-checkpoint_epoch2}.private.jsonl`
- calibration: `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/student-labels-calibration-student-{base-checkpoint_epoch1,v1-checkpoint_epoch1,v1-checkpoint_epoch2}.private.jsonl`
- forward real alerts: `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/student-forward-student-{base-checkpoint_epoch1,v1-checkpoint_epoch1,v1-checkpoint_epoch2}.private.jsonl`

Per-market tables:
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/tables-v1e2/student-tables.json`
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/tables-v1e2/teacher-tables.json`
  (Jev on the same held-out units)
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/tables-base/student-tables.json`

Inputs (write-once):
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/split.json`
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/prepare.json`
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/labels.private.jsonl`
  (snapshot of `/Users/wk/.local/share/means-of-prediction/slides/alerts-corpus-20261003/labels-alerts.private.jsonl`)
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/labels-cut.private.jsonl`
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007/calibration.private.json`
- Forward run: `/Users/wk/.local/share/means-of-prediction/alerts-forward-run-20261007`

Chain and logs (stage times UTC):
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007.chain.sh` and
  `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007.chain.log`
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007.train-v1.log` and
  `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007.train-base.log`
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007.eval-v1-epoch1.log`,
  `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007.eval-v1-epoch2.log` and
  `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007.eval-base-epoch1.log`
- `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007.battery-guard.sh`
  (pauses training at 8% battery when not charging)
- Superseded launches:
  - `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007-attempt1`
    (stopped after review)
  - `/Users/wk/.local/share/means-of-prediction/slides/alerts-student-20261007-attempt2`
    (a 401,025-label snapshot)

Code (branch `RonTuretzky/replace-astra-with-fable-research`):
- `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach/app/scripts/research/blind/alerts_student.py`
  (split, relabel-cut, prepare, train, evaluate)
- `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach/app/scripts/research/blind/laya_distill.py`
  (trainer; `--resume-every 250` mid-epoch resume points, commit 1167e32)
- `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach/app/scripts/research/blind/alerts_tables.py`
  (per-market K-outlet tables)

## Next

1. Approve the forward-test pre-registration before October 25: Jev at 0.7 as the frozen reader,
   and a student at 0.55 as a diagnostic beside it.
2. Retrain on the real alert stream once Jev has labelled it. Add the market creation date to the
   next Fable rules batch (the window-start fix).
3. Headline-only comparison.
