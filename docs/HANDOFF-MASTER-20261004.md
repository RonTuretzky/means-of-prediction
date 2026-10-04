# Means of Prediction: master handoff (October 4, 2026, 18:00 JST)

Read this first. It states the premise, gives a brief history of the whole research
effort, says what is best today and where it lives, what is running, and what to do next.
Detail documents are linked from each section; this file is meant to be enough on its own
to pick the work up.

## 1. Premise

**Product.** Means of Prediction is a prediction-market protocol whose settlement is a
proof over a DKIM-signed email from a news source: no oracle committee, anyone can open a
market and anyone can settle it by submitting the email (`README.md`,
`contracts/src/{market,dkim,judge,tokens}`). The deployed version verifies the RSA-SHA256
signature on-chain and matches a regular expression against the Subject or a bounded body
window (`docs/BODY-PARSING.md`, `docs/AUTO-SETTLEMENT.md`).

**Research question.** A regular expression cannot read. Can a model decide, from one
signed email, whether it reports a market's outcome as a completed fact, safely enough to
move money? Two constraints shape everything:

- The model that decides on-chain must be re-executable by anyone (the Gas Killer design,
  `docs/GASKILLER-LLM-SETTLEMENT.md`). A closed hosted model cannot be the judge.
- What matters is false settlement per market over its whole window against a submitter
  who can try many emails, not accuracy per email (`docs/RESEARCH-PLAN-V2.md`, threat
  model).

**Roles the research converged on.**

| role | who | why |
|---|---|---|
| rule writer | Claude Fable 5.1, blind to outcomes, through headless Claude Code under the owner's sign-in | turns public market terms into factual predicates for each side |
| teacher reader | Jev (TypeSafe closed decision model, `typesafe/jev-1.13` via OpenRouter, about $0.00005 per call) | reads well and is safe, but closed |
| deployable reader | Laya (421M ModernBERT typed-decision encoder, Apache-2.0, about 20 ms per call on a laptop GPU), distilled from Jev | open and re-executable |
| ground truth | human-reviewed labels on a sealed validation split; real market payouts only as a consistency check | payouts are never treated as proof that a document settles a market |

## 2. Brief history

| when | what happened | outcome |
|---|---|---|
| to Sept 13 | Regex rules and prose rules written by Astra (gpt-6-astra), judged by local Qwen3.5-35B-A3B on whole NYT newsletter emails. Market catalog built: 3.3M markets, 1.4M settling on "credible reporting". Development cohort: 143 NYT emails, 1,915 rows (161 factual, 1,520 synthetic controls, 91 weak, 143 unlabeled). | Regex plateaued; Qwen low recall. `docs/AGENT-HANDOFF-20260914.md`, `docs/QWEN-RESUME-HANDOFF.md` |
| Sept 14–16 | Astra replaced by Fable 5.1 as rule generator, run through headless Claude Code (no API key). Sealed validation split by market. Twelve-hour autonomous prompt-optimization loop. Judge swap test. | Fable as judge found 149 of 160 facts with zero false claims; Qwen 65 of 160. **The reader, not the rule writer, is the bottleneck.** Loop stopped at the owner's request. `docs/FABLE-ROUND-20260915.md`, `docs/FABLE-GENERATOR-TRANSPORT.md` |
| Sept 16–17 | Rethink. Only 1 of 161 facts was "answerable" under Polymarket's own fine print; 19 of 161 arrived before the market closed; a DKIM signature proves the domain, not the newsroom. | Research plan v2: admissible evidence, per-market false settlement, locate-then-judge, Subject-first slice, pre-registered forward test. Resolved credible-reporting pool of 63,368 markets. `docs/RESEARCH-PLAN-V2.md`, `docs/DATASET-V2-PLAN.md`, `docs/NEWSLETTER-SUBSCRIPTIONS.md` |
| Sept 21 | Benchmarked typed-decision models on located passages. | Jev: 137 of 161 correct side, 0 wrong. Base Laya: 56 right, 87 wrong side. Jev is the teacher; Laya needs training. `docs/LAYA-BENCHMARK-20260921.md` |
| Sept 22–27 | Distilled Laya from Jev on 1,200-character windows of the newsletter emails. v1 under-fired; v2 re-weighted positives; found the choice head broken and the side heads sound; v3 (student-proposed hard negatives) collapsed; v3b (positives embedded in real newsletter text) fit the teacher but confused sides; v3c added side-contrast weighting. | **v3c epoch 2: 41 of 56 held-out facts correct, 1 wrong side, 0 false picks on 105 unsettled rows; Jev 48 / 0 / 2.** `docs/LAYA-DISTILLATION-20260922.md`, `docs/HANDOFF-LAYA-DISTILLATION-20260927.md` |
| Oct 2–4 | Pivot of the evidence source: Google Alerts emails instead of newspaper newsletters (one google.com signer covers every outlet; a result is about 250 characters). Verified the email anatomy on real messages, red-teamed "one alert per newspaper, headline only", built an alert-shaped corpus for 19,783 resolved markets, started Jev labels, created live alerts on the owner's Gmail. | Headline-only with K outlets fails (sibling and date-bucket false YES, recall collapse); revised design adopted. Corpus and labels in progress. `docs/GOOGLE-ALERTS-PLAN-20261003.md`, `docs/HANDOFF-GOOGLE-ALERTS-20261003.md` |

## 3. What is best today

**The newsletter student (finished).** Checkpoint
`~/.local/share/means-of-prediction/slides/laya-distill-jev-v3b-20260925/student-v3c/checkpoint_epoch2`
(1.6 GB). Use the per-side heads, not the choice head: ask the two factual statements as
separate yes/no questions, take the larger probability if it is at least 0.4 (threshold
fixed in advance on training-market rows), else abstain.

| reader | 56 held-out facts: correct / wrong side / abstain | false picks on 105 unsettled rows |
|---|---|---|
| base Laya (choice head) | 22 / 26 / 8 | 11 |
| v2 epoch 1, side heads at 0.4 | 34 / 2 / 20 | 1 |
| v3c epoch 2, side heads at 0.4 | 41 / 1 / 14 | 0 |
| Jev | 48 / 0 / 8 | 2 |

Recipe that produced it (`app/scripts/research/blind/laya_distill.py`): Jev soft labels on
(window, market) units; choice sequences dropped; short synthetic positives embedded four
times in real-newsletter filler and real positives re-cropped, all re-labelled by Jev;
positive weight 2; **side-contrast weight 4** (on a unit where one side is a teacher
positive, the other side's negative sequence is weighted like a positive); two epochs from
the v2 epoch-1 weights. Caveat: the split is by market, not by email text; 50 of the 56
facts sit in emails that also appear in training under other markets, so a forward test is
the honest measure.

Lessons that cost time: the choice head is broken (wrong sides 14 to 2 just by reading the
side heads); hard negatives alone silence the student on real newsletter text; only 31
real newsletter positives exist in training, 407 are short synthetic passages; a closed
laptop lid sleeps the machine unless `caffeinate -i -s` is held; training on battery died
at 3%.

**The alerts track (in progress).** Design after the adversarial review: one topical alert
per market with the query frozen and bound to the signed Subject; outlet identity only
from the article URL host inside the result, against an allowlist; the judge reads
headline + publisher label + snippet + the signed send time + the Fable rule; markets
admitted only if a headline can carry the outcome (no "on date X" buckets or thresholds,
siblings by exclusivity); K counted over independent originations; independent collectors
logging every email on arrival; newsletters kept as a second evidence class. Evidence for
the review, Jev reading headlines only on a 120-market probe: at the setting with near-zero
false YES only about one in five true-YES markets settles, and raising K does not help.

## 4. Where everything is

Repository worktree: `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach`,
branch `RonTuretzky/replace-astra-with-fable-research`, remote `origin`
(`RonTuretzky/means-of-prediction`). Commit as the configured user, no assistant
co-author trailer. Private data: `~/.local/share/means-of-prediction/` (never commit
`*.private.*`, raw mail or keys). Secrets: `~/.config/means-of-prediction/openrouter.json`.
Python: `~/.local/share/means-of-prediction/venv-laya-py312/bin/python` for anything that
touches Laya or torch; `venv-research-py314` for the older round scripts.

Code, all in `app/scripts/research/blind/`:

| file | role |
|---|---|
| `fable_transport.py`, `fable_round.py`, `fable_autorun.py`, `fable_judge.py`, `qwen_round1.py` | Fable generator transport, the Fable/Qwen round, the judge swap |
| `laya_bench.py`, `heldout_view.py`, `compare_students.py` | benchmark on the 730-row human-labelled subset (`--model-path`, `--side-threshold 0.4`), held-out view, side-by-side of students |
| `laya_distill.py` | distillation: `label`, `label-active`, `label-augment`, `prepare`, `train`, `evaluate`; GPU pacing (`--gpu-share auto`) |
| `alerts_email.py` | parse a raw Google Alerts email into result units (`unit_text`) |
| `rules_batch.py` | batched blind Fable rules per market |
| `gal_download.py`, `gal_index.py` | GDELT Article List download; SQLite FTS5 index and per-market pairing in alert shape |
| `alerts_label.py` | Jev labels on (alert unit, market) pairs with the Fable rule |
| `alerts_probe.py` | 120-market calibration probe on Google News headlines (not for bulk use) |

Private artifacts under `~/.local/share/means-of-prediction/`:

| path | contents |
|---|---|
| `slides/fable-qwen-nyt-round1-20260915/` | the round: emails and labels, public market inputs, Fable rules, sealed `validation-split.json` |
| `slides/fable-judge-baseline-20260915/` | Fable judge arm and located evidence quotes |
| `slides/jev-benchmark-20260921/jev-1.13/`, `slides/laya-benchmark-20260921/student-*/` | benchmark rows for Jev and every student |
| `slides/laya-distill-jev-20260922/`, `…-v3-20260924/`, `…-v3b-20260925/` | distillation roots: labels, prepared sequences, evaluations, checkpoints (`student-v3c/checkpoint_epoch2` is the one to use) |
| `dataset-v2-20260916/market-pool-v2/market-pool.jsonl` | 63,368 resolved credible-reporting markets with payouts as private observations |
| `historical-market-catalog-20260914/catalog.sqlite3` | full market catalog (9.5 GB) |
| `gdelt-gal/en/*.jsonl.gz`, `gdelt-gal/gal.sqlite3` | GDELT Article List, English, 2025-05-20 to 2026-09-16 (485 days); full-text index, 55.9M articles |
| `slides/alerts-corpus-20261003/` | `sample.private.json` (19,783 markets, all 10,390 event groups, up to 3 each), `pairs.private.jsonl` (17,465 markets with units, 714,789 units), `labels-alerts.private.jsonl` (Jev labels, growing) |
| `slides/alerts-rules-20261003/rules.jsonl` | Fable rules for 19,453 of the 19,783 markets |
| `slides/alerts-probe-20261002/` | calibration probe: headlines, Jev and student judgements, summary |
| `slides/*.sh`, `slides/*.log` | chain scripts and their one-line-per-stage logs |

Live alerts on the owner's Gmail (created October 3 by hand through the Alerts page): 18
event-level alerts for open market families, 5 outlet census alerts, 2 RSS probes; list,
settings and feed URLs in `docs/HANDOFF-GOOGLE-ALERTS-20261003.md`.

## 5. Running now

| job | state | how to check or relaunch |
|---|---|---|
| Jev labels on the alert-shaped corpus | 82,645 of about 550,000 pairs; the chain is waiting for the OpenRouter key's $1 daily limit to reset and resumes on its own | `slides/alerts-label.log`; relaunch `nohup ~/.local/share/means-of-prediction/slides/alerts-label.sh > …/slides/alerts-label.log 2>&1 &` |
| Fable rules | finished: 19,453 rules; 330 markets missing from 13 failed batches | rerun `rules_batch.py --root …/alerts-rules-20261003 --sample …/sample.private.json` with `MOP_CLAUDE_CODE_BIN="$CLAUDE_CODE_EXECPATH"` (a stale `~/.local/bin/claude` fails every batch with `model_mismatch`) |
| Google Alerts mail | accruing in the owner's Gmail since October 3 | export raw messages with full headers; parse with `alerts_email.py` |

No training is running.

## 6. Next steps, in order

1. Finish the Jev labels (a day or two at the key's limit; hours if the owner raises it).
2. Payout-consistency and coverage tables per market at K = 1, 2, 3 using the Fable rules,
   with the admission rule applied; this is the first large-scale false-settlement number.
3. Distil the alert-shaped student with the v3c recipe, input = headline + publisher +
   snippet; compare with headline only.
4. Pull the first real alert emails, measure how far the GDELT stand-in is from what
   alerts deliver (URL and host overlap, headline rewriting, snippet versus description,
   delay), and apply Google's truncation to the training text.
5. Pre-registered forward test on the open markets behind the 18 alerts, threshold fixed
   in advance, both students (newsletter and alert-shaped).
6. Contract work for an alerts market type, after the format census: signer pin on
   `googlealerts-noreply@google.com` and the key hash, outlet host allowlist from the
   result's URL, a body profile for the quoted-printable HTML part, and never Subject
   evidence from this signer.

## 7. Open items for the owner

- Raise or remove the $1/day limit on the OpenRouter key, then rotate the key (it was
  pasted in chat once).
- Decide on a dedicated Google account for evidence collection; the alerts currently sit
  on a personal Gmail.
- Still owed from research plan v2: the newsletter mailbox subscriptions, Guardian and
  NYT API keys, a decision on publishing paywalled newsletter text.
