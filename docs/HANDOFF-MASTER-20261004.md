# Means of Prediction: master handoff (October 4, 2026, 18:00 JST)

Read this first. It states the premise, gives a brief history of the whole research
effort, says what is best today and where it lives, what is running, and what to do next.
The September 14 handoffs (`docs/AGENT-HANDOFF-20260914.md`, `docs/QWEN-RESUME-HANDOFF.md`)
are history only: their worktree, branch, remote and judge instructions no longer apply.

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
  Verifiable execution of the Laya student (pinned weights, deterministic inference, the
  re-execution fleet) is **not built and has no owner**; every result below is an
  off-chain measurement.
- What matters is false settlement per market over its whole window against a submitter
  who can try many emails, not accuracy per email (`docs/RESEARCH-PLAN-V2.md`, threat
  model).

**Settlement rule the research assumes** (from research plan v2). A market resolves YES
when at least K admissible sources each report the dated event as a completed fact inside
the evidence window, and the YES becomes final after a challenge delay. A model is never
asked to prove a negative: NO is reached only by exclusivity (a sibling market in the same
event group settles YES) or the market voids at par at the deadline. Terms: *siblings* are
markets on mutually exclusive outcomes of one event (each candidate for one office);
a *date bucket* is a market that differs from a sibling only by a date ("IPO on June 26",
"by October 31"); *independent originations* means K separate reports, not K hosts carrying
one wire story.

**Roles the research converged on.**

| role | who | why |
|---|---|---|
| rule writer | Claude Fable 5.1, blind to outcomes, through headless Claude Code under the owner's sign-in | turns public market terms into factual predicates for each side (A = first outcome label, B = second) |
| teacher reader | Jev (TypeSafe closed decision model, `typesafe/jev-1.13` via OpenRouter, about $0.00002 to $0.00005 per call) | reads well and is safe, but closed |
| deployable reader | Laya (421M ModernBERT typed-decision encoder, Apache-2.0, about 20 ms per call on a laptop GPU), distilled from Jev | open weights; see the caveat on verifiable execution above |
| yardstick | reviewed labels on a sealed validation split; real market payouts only as a consistency check | the labels come from the round's retrospective review of each (market, email) pair, not from an independent human gold set (the Laya documents call them "human labels"; read that as these reviewed labels). Payouts are never proof that a document settles a market |

## 2. Brief history

| when | what happened | outcome |
|---|---|---|
| to Sept 13 | Regex rules and prose rules written by Astra (gpt-6-astra), judged by local Qwen3.5-35B-A3B on whole NYT newsletter emails. Development cohort: 143 NYT emails, 1,915 rows (161 factual, 1,520 synthetic controls, 91 weak, 143 unlabeled). | Regex plateaued; Qwen low recall. `docs/QWEN-RESUME-HANDOFF.md` |
| Sept 14–16 | Market catalog finished (3.3M markets; 1.4M settle on "credible reporting"). Astra replaced by Fable 5.1 as rule generator, run through headless Claude Code (no API key). Validation split sealed by market. Twelve-hour autonomous prompt-optimization loop. Judge swap test. | Fable as judge found 149 of 160 facts with zero false claims; Qwen 65 of 160. **The reader, not the rule writer, is the bottleneck.** Loop stopped at the owner's request. `docs/AGENT-HANDOFF-20260914.md`, `docs/FABLE-ROUND-20260915.md`, `docs/FABLE-GENERATOR-TRANSPORT.md` |
| Sept 16–17 | Rethink. Only 1 of 161 facts was "answerable" under Polymarket's own fine print; 19 of 161 arrived before the market closed; a DKIM signature proves the domain, not the newsroom. Locate-then-judge tried with the re-executable Qwen on passages Fable had located. | Research plan v2. Qwen on located passages: 45 of 160 in the five-field format, 11 of 161 as one yes/no per claim, zero false claims either way: **the re-executable LLM is safe but nearly useless as a reader**, so the plan's fallback, distilling a small open judge, was taken. Resolved credible-reporting pool of 63,368 markets. `docs/RESEARCH-PLAN-V2.md`, `docs/DATASET-V2-PLAN.md`, `docs/NEWSLETTER-SUBSCRIPTIONS.md` |
| Sept 21 | Benchmarked typed-decision models on the located passages. | Jev: 137 of 161 correct side, 0 wrong. Base Laya: 56 right, 87 wrong side. Jev is the teacher; Laya needs training. `docs/LAYA-BENCHMARK-20260921.md` |
| Sept 22–27 | Distilled Laya from Jev on 1,200-character windows of the newsletter emails. v1 under-fired; v2 re-weighted positives and exposed the broken choice head; v3 (student-proposed hard negatives) collapsed; v3b (positives embedded in real newsletter text) fit the teacher but confused sides; v3c added side-contrast weighting. | **v3c epoch 2: 41 of 56 held-out facts correct, 1 wrong side, 0 false picks on 105 unsettled rows; Jev 48 correct, 0 wrong, 2 false picks.** `docs/LAYA-DISTILLATION-20260922.md`, `docs/HANDOFF-LAYA-DISTILLATION-20260927.md` |
| Oct 2–4 | Pivot of the evidence source: Google Alerts emails instead of newspaper newsletters (one google.com signer covers every outlet; one result is about 250 characters). Verified the email anatomy on real messages, red-teamed "one alert per newspaper, headline only", built an alert-shaped corpus for 19,783 resolved markets, started Jev labels, created live alerts on the owner's Gmail. | Headline-only with K outlets fails (sibling and date-bucket false YES, recall collapse); revised design adopted. Corpus built, labels in progress. `docs/GOOGLE-ALERTS-PLAN-20261003.md`, `docs/HANDOFF-GOOGLE-ALERTS-20261003.md` |

**Status of research plan v2.** In force: the threat model, the settlement rule above,
the stop/keep list. Not run: the Track 0 censuses, the Subject-first slice on Sepolia,
gates G1 and G2 (distillation was started directly after the September 21 benchmark).
Replaced: Track 3 newsletter subscriptions never arrived and the alerts track took their
place. Reduced: the Track 4 forward test survives as next-step 1 below.

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
| Jev, side heads at 0.4 | 48 / 0 / 8 | 2 |

How to read that table. A *fact* is a (market, email) pair where the email states the
market's outcome; the round has 161 of them, 56 in the held-out markets. The readers were
scored on an excerpt of about 800 characters around the sentence Fable had already
located, so the numbers measure judging given a locator. The locator-free measure is the
whole-email sweep in the distillation write-up (3 fires on 37 weak rows at 0.5 for v3c).
The 105 *unsettled rows* are 60 synthetic negative controls plus 45 weak or unrelated
emails. The split is by market, not by email text: 50 of the 56 facts sit in emails that
also appear in training under other markets, so a forward test is the honest measure.

Recipe (`app/scripts/research/blind/laya_distill.py`): Jev soft labels on (window, market)
units; choice sequences dropped; short synthetic positives embedded four times in
real-newsletter filler and real positives re-cropped, all re-labelled by Jev; positive
weight 2; **side-contrast weight 4** (on a unit where one side is a teacher positive, the
other side's negative sequence is weighted like a positive); two epochs from the v2
epoch-1 weights.

Lessons that cost time: the choice head is broken (wrong sides 14 to 2 just by reading the
side heads); hard negatives alone silence the student on real newsletter text; only 31
real newsletter positives exist in training, 407 are short synthetic passages; a closed
laptop lid sleeps the machine unless `caffeinate -i -s` is held; training on battery died
at 3%.

**The newsletter student must not be used on alert text.** On the 120-market probe
(55 YES and 56 NO markets with headlines, registry outlets, headline only) the v3c student
at its 0.4 threshold reads 14 of the 56 NO markets as YES at K = 1 and 8 at K = 2. It was
trained on newsletter windows, not headlines. That is why an alert-shaped student is the
next training job.

**The alerts track (in progress).** Design after the adversarial review
(`docs/GOOGLE-ALERTS-PLAN-20261003.md`):

- One topical alert per market, the query frozen at market creation. The signed Subject is
  the alert owner's own query text, so it may identify which frozen query an email belongs
  to, but it can never carry the outcome, and the google.com key must stay out of every
  registry used by Subject or Subject-or-body markets.
- The signature proves Google sent the text, not that the outlet published it, so outlet
  identity comes only from the article URL host inside the result, against an allowlist.
- The judge reads headline + snippet + the Fable rule; the contract, not the judge,
  enforces the date window from the signed send time. Markets are admitted only if a
  headline can carry the outcome (no date buckets or thresholds; siblings by exclusivity).
- K counted over independent originations, a challenge delay, independent collectors
  logging every email on arrival, newsletters kept as a second evidence class.
- The deployed verifier currently rejects alert emails (multipart body); a body profile
  for the quoted-printable HTML part is needed.

Evidence behind the review, Jev reading headlines only on the same probe, registry
outlets: at p ≥ 0.7, false YES 1 of 56 at K = 1, 2 and 3; true YES 12, 9 and 6 of 55.
Raising K removes true settlements as fast as false ones.

What the teacher is shown today, and two open decisions. `alerts_label.py` gives Jev the
headline, the publisher label and the snippet, and asks the market question plus the
rule's factualA and factualB. It does not show the send time, the rule's event instance
or its not-counted list, and the text is GDELT's untruncated title and description, not
Google's 100 and 160 character cut. Decide before distilling: (1) truncate and relabel the
long units, or accept and measure the mismatch against real alerts; (2) whether event
instance belongs in the judge's input or stays a contract-side filter.

Limits of the GDELT stand-in, so the first tables are not over-read: it has almost no
Reuters, AP, Washington Post, WSJ, Politico, FT, Axios or USA Today records; only 4% of
paired units sit on registry-outlet hosts; 41% of the sampled markets are sports-season
questions, so report per topic; units are entity-matched records from ten days before the
market closed to two days after, capped at 60 per market (the 40 best-matching are
labelled), which is not what an alert query would have returned.

## 4. Where everything is

Repository worktree: `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach`,
branch `RonTuretzky/replace-astra-with-fable-research`, remote `origin`
(github.com/RonTuretzky/means-of-prediction; `origin` is correct in this worktree). Commit
as the configured user, no assistant co-author trailer. Private data:
`~/.local/share/means-of-prediction/` (never commit `*.private.*`, raw mail or keys).
Secrets: `~/.config/means-of-prediction/openrouter.json` (teacher key),
`~/.config/means-of-prediction/mailbox.json` (IMAP; it is the same Gmail account that
receives the alerts). Python:
`~/.local/share/means-of-prediction/venv-laya-py312/bin/python` for everything in the Laya
and alerts tracks; `venv-research-py314` only for the older round scripts.

**Do not open, do not redo.** The sealed evaluation reservations listed in
`docs/AGENT-HANDOFF-20260914.md` (the 12-question/120-fixture evaluation and the
two-email/241-question annotations) and the `validationCaseIds` of the round stay unopened
for planning or training. Finished roots are write-once; new runs get new directories.
Closed lines of work: the prompt-optimization loop on the 161 pairs, "answerable under
Polymarket rules" as a metric, NYT article text through blocked routes, a hosted frontier
model as the arbiter. `slides/alerts-corpus.sh` is the superseded Google News chain; do
not run it.

Code, all in `app/scripts/research/blind/`:

| file | role |
|---|---|
| `fable_transport.py`, `fable_round.py`, `fable_autorun.py`, `fable_judge.py`, `qwen_round1.py` | Fable generator transport, the Fable/Qwen round, the judge swap |
| `laya_bench.py`, `heldout_view.py`, `compare_students.py` | benchmark on the 730-row reviewed subset (`--model-path`, `--side-threshold 0.4`), held-out view, side-by-side of students |
| `laya_distill.py` | distillation: `label`, `label-active`, `label-augment`, `prepare`, `train`, `evaluate`; GPU pacing (`--gpu-share auto`). Hard-wired to the newsletter round's files; the alert corpus needs an adapter |
| `alerts_email.py` | parse a raw Google Alerts email into result units (`unit_text`) |
| `rules_batch.py` | batched blind Fable rules per market |
| `gal_download.py`, `gal_index.py` | GDELT Article List download; SQLite FTS5 index and per-market pairing in alert shape |
| `alerts_label.py` | Jev labels on (alert unit, market) pairs with the Fable rule |
| `alerts_probe.py` | 120-market calibration probe on Google News headlines (not for bulk use); its `summary()` is the template for the K-outlet tables |

Mail intake: `app/automation/imap.mjs`, `app/automation/collector.mjs`,
`app/scripts/mailbox.mjs` (reads `mailbox.json`).

Private artifacts under `~/.local/share/means-of-prediction/`:

| path | contents |
|---|---|
| `slides/fable-qwen-nyt-round1-20260915/` | the round: emails and labels, public market inputs, Fable rules, sealed `validation-split.json` |
| `slides/fable-judge-baseline-20260915/` | Fable judge arm and located evidence quotes |
| `slides/jev-benchmark-20260921/jev-1.13/`, `slides/laya-benchmark-20260921/student-*/` | benchmark rows for Jev and every student |
| `slides/laya-distill-jev-20260922/`, `slides/laya-distill-jev-v3-20260924/`, `slides/laya-distill-jev-v3b-20260925/` | distillation roots: labels, prepared sequences, evaluations, checkpoints (`student-v3c/checkpoint_epoch2` in the last one is the checkpoint to use) |
| `dataset-v2-20260916/market-pool-v2/market-pool.jsonl` | 63,368 resolved credible-reporting markets; the payout is in `privateObservation.outcome` |
| `historical-market-catalog-20260914/catalog.sqlite3` | full market catalog (9.5 GB) |
| `gdelt-gal/en/`, `gdelt-gal/gal.sqlite3` | GDELT Article List, English, 2025-05-20 to 2026-09-16 (485 daily files); full-text index, 55.9M articles |
| `slides/alerts-corpus-20261003/` | `sample.private.json` (19,783 markets: every event group that has a binary Yes/No market, 10,390 of the pool's 10,450, up to 3 each; payout per market in `payout`), `pairs.private.jsonl` (17,465 markets with units, 714,789 units), `labels-alerts.private.jsonl` (Jev labels, growing; records carry ids and probabilities, the text is in the pairs file) |
| `slides/alerts-rules-20261003/rules.jsonl` | Fable rules for 19,453 of the 19,783 markets |
| `slides/alerts-probe-20261002/` | calibration probe: headlines, Jev and student judgements, summary |
| `slides/alerts-forward-20261003/` | `alert-market-map.json` (each alert query, its open markets with ids and close dates), `open-markets-20261003.json` (the snapshot) |

Chain scripts and their one-line-per-stage logs sit in `slides/` (`alerts-label.sh`,
`laya-distill-v3c.sh` and the older ones).

Live alerts on the owner's Gmail, created October 3 by hand through the Alerts page:
18 event-level alerts, 5 outlet census alerts (whole-outlet streams, to measure volume,
truncation and results per email), 2 RSS probes (unsigned, for per-entry timestamps).
List, settings and feed URLs in `docs/HANDOFF-GOOGLE-ALERTS-20261003.md`. Open markets
behind them:

| alert query | open markets | closes |
|---|---|---|
| Serbia prime minister | 1 | Oct 25 |
| Israel next prime minister | 18 siblings | Oct 28 |
| Russia Ukraine ceasefire agreement; NATO Russia military clash; Israel Iran ceasefire; US Iran nuclear deal; Anthropic IPO; "Kanye West" Russia; "Strait of Hormuz" fees | 10, all "by October 31" or "through" date markets | Oct 31 to Nov 1 (one Nov 30) |
| midterm elections House control / Senate control / governor results; California billionaire wealth tax | 34 | Nov 4 |
| "Cy Young" award winner | 1 | Nov 12 |
| "GTA 6" release date | 1 | Nov 20 |
| Nobel Prize winner announced; Federal Reserve interest rate decision; government shutdown ends | none in the snapshot; kept as format and delay probes around scheduled events | n/a |

## 5. Running now

| job | state | how to check or relaunch |
|---|---|---|
| Jev labels on the alert-shaped corpus | **running** (chain alive, waiting for the key's daily limit). 82,645 of 520,552 pairs, 2,688 markets, $2.01 spent. About 41,000 pairs per dollar, so 437,907 remaining pairs are about 11 more days at $1/day or about $11 in a few hours if the owner raises the limit. Stage log times are UTC. | check `pgrep -fl alerts-label`; only if nothing prints, relaunch with `nohup caffeinate -i -s ~/.local/share/means-of-prediction/slides/alerts-label.sh >> ~/.local/share/means-of-prediction/slides/alerts-label.log 2>&1 &` on AC power. Never start a second copy |
| Fable rules | finished: 19,453 rules. 330 markets missing: 325 from 13 batches that ended in `error_max_turns`, 5 dropped from completed batches | rerun with a smaller batch: `rules_batch.py --root …/slides/alerts-rules-20261003 --sample …/slides/alerts-rules-20261003/sample.private.json --batch 10`, with `MOP_CLAUDE_CODE_BIN` set to a Claude Code binary of version 2.1.251 or newer (the variable `CLAUDE_CODE_EXECPATH` exists only inside a Claude Code session; a stale `~/.local/bin/claude` 2.1.236 fails every batch with `model_mismatch`). It draws on the owner's Claude session limit. The label chain's next pass picks the new rules up |
| Google Alerts mail | 477 emails (3,226 results) pulled on October 6, all from Gmail's **Spam** folder; raw messages under `~/.local/share/means-of-prediction/alerts-mail-20261006/raw/`, census in `census.json`, GDELT comparison in `fidelity.json` (only 22% of alert results exist in GDELT; no Reuters, AP, NYT, WaPo). Spam is purged after 30 days, so pull again with `alerts_mail.py` at least weekly until a filter exists | export raw messages with full headers through the IMAP intake above (sender `googlealerts-noreply@google.com`); never publish a raw message (recipient address and a live per-alert token are in the signed body); record the google.com DKIM TXT record for the selector seen (currently `20251104`) at each pull; parse with `alerts_email.py` |

No training is running.

## 6. Next steps, in order

1. **Pre-register the forward test now; the first deadline is October 25** (Serbia), then
   October 28 (Israel) and October 31. A pre-registration written after outcomes are
   public is worthless. Freeze and hash: the markets and their siblings
   (`alert-market-map.json`), the alert queries, the reader and threshold, K, the outlet
   allowlist and the admission rule. The alert-shaped student will not exist before the
   first events, so the reader that can be frozen today is Jev as an off-chain reference
   (headline + snippet, p ≥ 0.7, registry outlets) with the newsletter student reported
   beside it as a known-unsafe baseline. Most of the "by October 31" markets are date
   buckets, which the admission rule excludes from evidence-based NO; say so in the file.
   Start hash-logging alert emails on arrival.
2. Finish the Jev labels (see the row above). A preliminary version of step 3 can be
   computed today on the 2,688 labelled markets.
3. K-outlet tables, the first large-scale false-settlement number. No script exists yet;
   `alerts_probe.py summary()` is the template. Definitions: a unit claims YES when
   pA ≥ t (report t = 0.5 and 0.7; A is Yes for these markets) and its `seenAt` is inside
   the market window; a market settles when K distinct hosts claim; false YES = markets
   whose payout is No that reach K; coverage = markets whose payout is Yes that reach K.
   Report for all hosts and registry hosts, per topic, with denominators, and with the
   admission rule applied as a filter (it needs a tagging pass over the market questions:
   date bucket, threshold, ordinal, sibling family; nothing implements it yet).
4. Alert-shaped student. The GDELT corpus is the wrong outlet mix (see the plan's October 6 section); prefer the real alert stream for units, with Jev labels on real results. Needs an adapter (join labels to unit text from the pairs file,
   build Laya sequences) and a split by event group sealed before training, with the
   latest month held out. Carries over from the v3c recipe: no choice sequences, positive
   weight, side-contrast weight; the newsletter augmentation does not apply to
   250-character units. Start from the base Laya weights and from v3c epoch 2 and compare.
   Yardstick: agreement with Jev on held-out groups plus the step-3 tables; compare
   headline only against headline + snippet. Resolve the two open decisions in section 3
   first.
5. First real alert emails: pull, parse, and measure how far the GDELT stand-in is from
   what alerts deliver (URL and host overlap, headline rewriting, snippet versus
   description, delay), then fix the truncation transform. Two weeks of mail is enough for
   a first estimate; this is also the format census that gates step 7 (as-it-happens
   email size and result count, digest shape, the alert-count limit).
6. Run the forward test as pre-registered and report it.
7. Contract work for an alerts market type, after the census: signer pin on
   `googlealerts-noreply@google.com` and the key hash, outlet host allowlist from the
   result's URL, a body profile for the quoted-printable HTML part. Separately, someone
   must own verifiable execution of the student.

## 7. Open items for the owner

- Raise the OpenRouter key's limit by about $11 (or remove the $1/day cap), then rotate
  the key; it was pasted in chat once.
- Decide on a dedicated Google account for evidence collection; the alerts currently sit
  on a personal Gmail, which the trust rules say should not be the custodian.
- Approve the forward-test pre-registration before October 25.
- Still owed from research plan v2: Guardian and NYT API keys, a decision on publishing
  paywalled newsletter text. The newsletter mailbox subscriptions were overtaken by the
  alerts track.
