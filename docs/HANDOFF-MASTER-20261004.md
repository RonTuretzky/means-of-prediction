# Means of Prediction: master handoff (October 4, 2026, 18:00 JST; revised October 7, 13:30 JST)

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
event group settles YES) or the market voids at par when no YES is final by the deadline
plus a grace period (7 days in the research plan v2 template). Terms: *siblings* are
markets on mutually exclusive outcomes of one event (each candidate for one office);
a *date bucket* is a market that differs from a sibling only by a date ("IPO on June 26"
beside "IPO on June 27", "through October 31" beside "through November 30"); a standalone
"will X happen by T" market is not a bucket and voids at par when no YES is final by T
plus the grace period (a YES becomes final only after the challenge delay); *independent originations* means K separate reports, not K hosts carrying
one wire story.

**Roles the research converged on.**

| role | who | why |
|---|---|---|
| rule writer | Claude Fable 5.1, blind to outcomes, through headless Claude Code under the owner's sign-in | turns public market terms into factual predicates for each side (A = first outcome label, B = second) |
| teacher reader | Jev (TypeSafe closed decision model; `jev-latest` on the direct TypeSafe API, which the API reported as jev-1.13.0 on October 7 (logged in the forward run's `.judge-jev.log` for its second pass; the judge has printed the resolved id only since that day), $0.042 per million input tokens, output free, no daily cap; `typesafe/jev-1.13` through OpenRouter is used only when no TypeSafe key file exists, about $0.00002 to $0.00005 per call with a $1/day key limit) | reads well and is safe, but closed |
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
| Oct 6–7 | First real alert mail: 477 emails (3,226 results) pulled from the owner's Gmail, every one filed in Spam; format census and comparison with GDELT. Jev moved to the direct TypeSafe API. Dry run of the forward test: every result of the 15 alert families that have open markets, read against those markets by Jev, Fable and the newsletter student. | GDELT holds only 22% of what alerts deliver (no Reuters, AP or WaPo; 4 of 147 NYT). **At Jev's threshold no reader claimed YES on any of the 60 open markets** over 7,635 distinct result-market pairs; the newsletter student at its own 0.4 threshold claimed YES on 8 markets, every one false. Fable found the Kanye West Russia concert cancellation in 54 results on 41 hosts (25 in the headline, mostly wire copy; 29 only in the snippet, almost all sidebar or bulletin text), evidence against that market but not a settlement under the rule. Section 3, "Forward-test dry run". |

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

**First K-outlet table (preliminary, October 7, 14:00 JST, `alerts_tables.py`).** Jev labels
on the GDELT stand-in corpus, 345,358 labels over 11,367 markets of the 17,465 with
units (the chain was still running), units dated on or before the market's close date,
payouts as a consistency check only. A market reaches K when K distinct hosts carry a
result with pA at or above the threshold.

| Jev threshold | hosts | K | YES-payout markets reaching K (coverage) | NO-payout markets reaching K (false YES) |
|---|---|---|---|---|
| 0.5 | all | 1 | 993 of 4,261 (23.3%) | 60 of 6,911 (0.87%) |
| 0.7 | all | 1 | 544 of 4,261 (12.8%) | 11 of 6,911 (0.16%) |
| 0.7 | all | 2 | 316 of 4,261 (7.4%) | 5 of 6,911 (0.07%) |
| 0.7 | registry | 1 | 80 of 4,261 (1.9%) | 5 of 6,911 (0.07%) |
| 0.7 | registry | 2 | 19 of 4,261 (0.4%) | 0 of 6,911 |

Per topic at 0.7, any host, K = 1: geopolitics is the only topic with a false-YES rate
above 0.2% (7 of 554; sports, elections and entertainment 0 of 2,716, 434 and 195).
Registry coverage is tiny because GDELT carries few registry outlets (section above);
coverage on real alerts is a different number and is not measured yet.

The ten NO-payout markets that reached K = 1 at 0.7 were read one by one against the
Polymarket rules and creation dates (`prices` lookups on October 7): seven are
"strike on X by <date>" buckets where the strike happened before the market was created
(US on Nigeria, created the day after the Christmas strike; US on Somalia; Hezbollah on
Cyprus; Pakistan on Afghanistan; Russia on Kyiv; Russia on Poland, a September incident
in a June op-ed; India on Pakistan, a 2022 incident) and the results report a true event
outside the market's window; two are borderline reads at 0.70 and 0.71 (an analysis
piece on Israel and Iran; a Doechii-praises-Gaga headline read as Gaga attending the
Met Gala); one is a threshold market ("Sinners" wins 3 or fewer Oscars), which the
admission rule excludes. So the reader's own error rate at 0.7 is about 2 of 6,911, and
the dominant failure is the event window: the blind rules name the deadline but not the
window start, because the rule writer is not given the market creation date. Give it
that date (the event instance must say "on or after <creation>") and make the judge
check it; the contract's send-time check cannot catch a report, dated inside the
window, of an event that happened before it.

**Forward-test dry run (October 7).** Not the pre-registered test (step 1 below is still
owed) but a rehearsal of the whole pipeline on the first five days of real alert mail,
October 2 to 6, so that the pre-registration freezes a procedure that has already run end
to end. `alerts_forward.py` pairs every result of an alert family with every open market
behind that family: 15 families, 60 open markets, 7,635 distinct result-market pairs
(7,835 judgements per reader, because the five balance-of-power markets sit under both
midterm families and their 40 shared results were read once per family; the script now
judges such pairs once), 694 distinct hosts. Fable wrote the 60 blind rules (3 batches,
no failures); three readers judged each pair. Jev and the student see the headline, the
publisher label and the snippet and answer the market question and the two predicates
as separate yes/no questions. Fable sees a market's results numbered in calls of at most
120 (29 markets took one call, 25 two and 6 three, the six being Anthropic IPO and the
five balance-of-power markets, which were called under each midterm family; 97 calls in
all, so it never saw a large market's full list together), with host and send time, plus the
rule's event instance and not-counted list, and must quote the words that state A or B
as a completed fact.

| reader | threshold | markets with a YES (A) claim | markets with a NO (B) claim | notes |
|---|---|---|---|---|
| Jev, direct API | p ≥ 0.7 | 0 of 60 | 1 | B: "Israel x Iran ceasefire continues through October 31?", one result from abc11.com (not a registry host) about US soldiers killed in Iranian attacks, a different instance |
| Jev | p ≥ 0.5 (near misses) | 2 | 3 | A: "Ukraine warns of rising risk of war" and a German aid package read as a Russia-Ukraine ceasefire agreement; a "gigs are canceled" headline read as Kanye performing. B: Iran-war items read as the Israel-Iran or US-Iran ceasefire ending; on "Israel x Iran ceasefire continues through October 31?" the B side reaches 6 hosts, 3 of them registry hosts, the one place where Jev's near misses pass K = 2 over registry hosts |
| Fable 5.1 | high or medium confidence | 0 of 60 | 1 | B: "Kanye West performs in Russia by October 31?", 54 results on 41 distinct hosts, 6 of them registry hosts. Only 25 of the 54 (24 hosts; among registry hosts only theguardian.com and news24.com) carry the cancellation in the headline, and most of those are Reuters or Guardian/PA copy; the other 29, including every bbc.com, reuters.com, newsweek.com and euronews.com hit, carry it only in the snippet, almost all as sidebar or bulletin text on unrelated articles (one, intellinews.com on the organiser's frozen accounts, is a related article that states the cancellation in its own lede). A handful of originations, not 41 |
| newsletter student v3c, side heads | p ≥ 0.7 (Jev's threshold) | 0 of 60 | 0 | |
| newsletter student v3c, side heads | p ≥ 0.4 (its own threshold, fixed in advance) | **8 of 60**: 13 results, 1 registry host (cnbc.com, "Trump reiterates pledge to send $5,000 checks as elections loom" read as Republicans holding both chambers) | 11 | every A claim is a false YES; none survives K = 2 over registry hosts; the B side reaches two registry hosts on three markets (Kanye and both Israel-Iran "continues through" markets) |

How to read it. None of the 60 markets has closed and none of their events has happened
(prices checked on October 7 and kept in `prices-20261007.json`: the only markets above
0.5 are midterm forecasts for November 4, that is ten safe House seats, Democratic House
control at 0.925, Democratic Senate control and the D Senate, D House balance at 0.645;
the Serbia favourite at 0.68; and the three "ceasefire continues" markets, which pay YES
when nothing happens), so any YES claim would have been false. At Jev's threshold there
were none: zero false YES at K = 1 over 7,635 pairs for Jev, for Fable and for the
student. That is the number with information in it; a true settlement could not have
appeared yet. The student at its own 0.4 threshold fails in the same direction as the
120-market probe, at a lower rate: false YES on 8 of the 60 markets at K = 1 over all
hosts (3 of them at K = 2), on 1 at K = 1 over registry hosts and on none at K = 2 over
registry hosts, against the probe's 14 of 56 at K = 1 and 8 at K = 2 over registry
outlets; it stays a known-unsafe baseline on alert text. Jev's near misses at p ≥ 0.5 show what
the 0.7 threshold is for.

Fable's Kanye finding is evidence against YES, and the market prices YES at 1.3%, but
under the settlement rule it is not a settlement: NO is never reached by evidence, only by
a sibling's final YES or by void when no YES is final by the deadline plus the grace
period, and this market has no sibling in the snapshot. The market itself is admissible (a headline can carry "Kanye West performs in
St Petersburg"); the defect is in the B predicate Fable had written for it, which reads
"October 31, 2026 passed without Kanye West giving a qualifying live in-person
performance in Russia; established by cancellation/postponement past the deadline or the
window closing". The rule itself names a cancellation as a way B is established, and
Fable as judge took the cancellation reports as stating B although the deadline had not
passed and the judge prompt asks for a completed fact. Jev was given the same B text and
did not take it (pB at most 0.26 over the 88 Kanye results). The B side of a standalone
"by T" market is a predicate a rule writer and a reader will both over-read, so B claims
are reported but never settle, and the rule-writing prompt should forbid "established by
cancellation" wording. What the admission rule has to keep out are the three "continues
through" markets, whose YES is the absence of an event that no headline can carry, and
the governorship count market ("exactly 28 or 29", a threshold).

K was counted over distinct hosts, which is a proxy for the rule: section 1 counts
independent originations, and `settle()` does no ownership or wire-family collapsing, no
near-identical-headline deduplication and no non-wire-original check. The Kanye B side
reached 6 registry hosts that way, four of them snippet-only sidebar mentions.

Private outputs: `~/.local/share/means-of-prediction/alerts-forward-run-20261007/`
(`pairs.private.json`, `judged-{jev,fable,laya}.private.jsonl`, `settle-fable.json`,
`settle-{jev,laya}-<threshold>.json`, `prices-20261007.json`,
`typesafe-models-20261007.json`, and Fable's per-chunk receipts under `fable/`: 92
directories for 97 calls, because the first run keyed receipts by market and offset only
and the Senate-family call overwrote the House-family first chunk of the five doubled
markets; all five lost calls completed with no claim and the judged file is complete).
The one-line settlement tables sit beside that directory:
`alerts-forward-run-20261007.settle-jev.txt` (0.7), `.settle-jev-0.5.txt`,
`.settle-fable.txt`, `.settle-laya.txt` (0.7), `.settle-laya-0.4.txt`. The Jev pass ran
outside the chain (`.judge-jev.log`; five pairs that failed in the first pass were judged
in a second, since the judge resumes from its output, and that second pass logged the
resolved model id jev-1.13.0; the first pass started after `jev.json` existed, so it was
direct too, but its log has no model line); the chain `alerts-forward-run-20261007.chain.sh` ran the
rules wait, the Fable judge and settle, and the student judge and settle at 0.7; the 0.5
and 0.4 tables were run by hand afterwards. The 60 open-market rules are
`slides/alerts-forward-20261003/rules/rules.jsonl`.

## 4. Where everything is

Repository worktree: `/Users/wk/conductor/workspaces/means-of-prediction/newport-beach`,
branch `RonTuretzky/replace-astra-with-fable-research`, remote `origin`
(github.com/RonTuretzky/means-of-prediction; `origin` is correct in this worktree). Commit
as the configured user, no assistant co-author trailer. Private data:
`~/.local/share/means-of-prediction/` (never commit `*.private.*`, raw mail or keys).
Secrets: `~/.config/means-of-prediction/jev.json` (direct TypeSafe key; when this file
exists every Jev call goes to the direct API and OpenRouter is not touched; there is no
automatic failover, a direct-API failure is retried on the same endpoint and then raised),
`~/.config/means-of-prediction/openrouter.json` (OpenRouter key, used only when
`jev.json` is absent),
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
| `alerts_mail.py`, `alerts_fidelity.py` | pull alert mail read-only over IMAP (every folder, Spam included), snapshot the google.com DKIM record, verify a sample, census; compare alert results with GDELT (URL and host+title overlap, headline and snippet agreement, delay) |
| `alerts_forward.py` | forward test on real alerts: `pairs`, `judge --backend laya|jev|fable` (resumes from the judged file; a market under two families is judged once; Fable receipts keyed family-market-offset), `settle --backend X --threshold t` (claims, distinct hosts, registry hosts per side, a market's entries merged across families with units deduplicated; writes `settle-X-t.json`, or `settle-fable.json`) |
| `alerts_probe.py` | 120-market calibration probe on Google News headlines (not for bulk use) |
| `alerts_tables.py` | K-outlet tables on the retrospective corpus from the Jev labels: coverage of YES-payout markets and false YES on NO-payout markets per threshold, host scope and K, per topic; writes `tables-<stamp>.json` beside the labels |

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
| `slides/alerts-forward-20261003/` | `alert-market-map.json` (each alert query, its open markets with ids and close dates), `open-markets-20261003.json` (the snapshot), `open-sample.json` (the 60 open markets in `rules_batch.py --sample` form, the input the open-market rules batch ran from; log `slides/alerts-forward-20261003.rules.log`), `rules/rules.jsonl` (Fable's 60 open-market rules) |
| `alerts-mail-20261006/` | the 477 raw alert emails (`raw/*.eml`, mode 0600, never publish), `dkim-dns.json` (selector 20251104 record at pull time), `census.json`, `results.private.jsonl` (parsed results), `fidelity.json` (alerts versus GDELT) |
| `alerts-forward-run-20261007/` | forward-test dry run: pairs, the three readers' judgements, settlement tables at each threshold, prices, the TypeSafe model list (section 3) |

Chain scripts and their one-line-per-stage logs sit in `slides/` (`alerts-label.sh`,
`laya-distill-v3c.sh` and the older ones), except the forward-test chain, which sits at
the data root beside its run directory: `alerts-forward-run-20261007.chain.sh`, stage log
`alerts-forward-run-20261007.chain.log`, and the per-stage `.judge-*.log` and
`.settle-*.txt` files next to it.

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
| Jev labels on the alert-shaped corpus | **running on the direct TypeSafe API** since 12:10 JST October 7, no daily cap. 229,453 of 520,552 pairs at 12:40 JST, about 48,000 pairs per hour at $0.024 per 1,000 pairs, so the remaining 291,000 pairs are about 6 hours and $7. Chain `slides/alerts-label.sh` (sleeps 30 minutes whenever a pass exits 3 on a teacher halt, then resumes where it stopped), stage log `slides/alerts-label.log`, pass log `slides/alerts-corpus-20261003.label.log`; stage log times are UTC. | check `pgrep -fl alerts-label`; only if nothing prints, relaunch with `nohup caffeinate -i -s ~/.local/share/means-of-prediction/slides/alerts-label.sh >> ~/.local/share/means-of-prediction/slides/alerts-label.log 2>&1 &` on AC power. Never start a second copy |
| Fable rules | finished: 19,453 rules for the resolved corpus, plus the 60 open-market rules for the forward test (3 batches, no failures). 330 resolved markets missing: 325 from 13 batches that ended in `error_max_turns`, 5 dropped from completed batches | rerun with a smaller batch: `rules_batch.py --root …/slides/alerts-rules-20261003 --sample …/slides/alerts-rules-20261003/sample.private.json --batch 10`, with `MOP_CLAUDE_CODE_BIN` set to a Claude Code binary of version 2.1.251 or newer (the variable `CLAUDE_CODE_EXECPATH` exists only inside a Claude Code session; a stale `~/.local/bin/claude` 2.1.236 fails every batch with `model_mismatch`). It draws on the owner's Claude session limit. The label chain's next pass picks the new rules up |
| forward-test dry run | **complete** (section 3). The Jev pass ran outside the chain (`.judge-jev.log`, done marker `.jev.done`, table `.settle-jev.txt`); the chain `alerts-forward-run-20261007.chain.sh` ran the Fable judge and settle and the student judge and settle at p ≥ 0.7 (`.chain.log`, times UTC); the 0.5 and 0.4 tables were run by hand | nothing to relaunch. After each new mail pull: `alerts_forward.py pairs`, then the three judges (they resume from the judged files; Fable needs `MOP_CLAUDE_CODE_BIN` as for the rules), then `settle` per backend and threshold |
| Google Alerts mail | 675 emails (5,752 results, October 2 to 6, 21:41 PT) after the second pull on October 7 at 14:00 JST (198 new; the first pull on October 6 had 477), all from Gmail's **Spam** folder; DKIM sample 40 of 40 verified; registry outlets are well represented in real alerts (reuters.com 474 results, bbc.com 342, apnews.com 279, nytimes.com 232), unlike GDELT. The per-query census also lists about 80 further alert queries with one or two emails each (sports, Nobel prizes, central-bank rates, OpenAI releases, New York rents) that this track did not create; raw messages under `~/.local/share/means-of-prediction/alerts-mail-20261006/raw/`, census in `census.json`, GDELT comparison in `fidelity.json` (only 22% of alert results exist in GDELT; no Reuters, AP or WaPo at all, 4 of 147 NYT). Spam is purged after 30 days, so pull again at least weekly until a filter exists | `~/.local/share/means-of-prediction/venv-laya-py312/bin/python app/scripts/research/blind/alerts_mail.py` (defaults `--root ~/.local/share/means-of-prediction/alerts-mail-20261006`, `--since 03-Oct-2026`, `--verify-sample 40`): logs in with `mailbox.json`, reads every IMAP folder read-only (Spam included) for sender `googlealerts-noreply@google.com`, stores only messages not already under `raw/` (re-running is safe), re-parses `raw/` with `alerts_email.py` into `census.json` and `results.private.jsonl`, verifies a DKIM sample and appends the google.com TXT record for each selector seen (currently `20251104`) to `dkim-dns.json`. Not the Node intake (`imap.mjs` feeds the automation store, not `raw/`). Never publish a raw message (recipient address and a live per-alert token are in the signed body) |

No training is running.

## 6. Next steps, in order

1. **Pre-register the forward test now; the first deadline is October 25** (Serbia), then
   October 28 (Israel) and October 31. The October 7 dry run (section 3) is the procedure
   to freeze: `alerts_forward.py` with Jev at p ≥ 0.7 as the frozen reader, registry
   hosts, K = 2 over distinct registry hosts stated in the file as a proxy that
   over-counts originations (or first add the plan's origination-collapsing step to
   `settle()` and freeze that), with Fable's quote-backed claims and the newsletter student
   at 0.4 reported beside it as diagnostics, not as settling readers. Apply the admission
   rule as the plan states it: the three "continues through" markets and the governorship
   count market are out; the seven standalone "by October 31" markets stay in on their
   YES side and void at par when no YES is final by T plus 7 days (research plan v2
   template), their B claims reported only; the Israel
   sibling family settles only by exclusivity. That leaves 56 of the 60 markets. A pre-registration written after outcomes are
   public is worthless. Freeze and hash: the markets and their siblings
   (`alert-market-map.json`), the alert queries, the reader and threshold, K, the outlet
   allowlist, the admission rule and the void grace period. The alert-shaped student will not exist before the
   first events, so the reader that can be frozen today is Jev as an off-chain reference
   (headline + snippet, p ≥ 0.7, registry outlets) with the newsletter student reported
   beside it as a known-unsafe baseline. Say in the file that no market settles NO by
   evidence, so B claims are reported and never settle.
   Start hash-logging alert emails on arrival.
2. Finish the Jev labels (hours away on the direct API, see section 5), then rerun
   `alerts_tables.py`. Before the next rules batch, add the market creation date to the
   rule writer's input so the event instance carries the window start (section 3, the
   ten-market audit).
3. K-outlet tables, the first large-scale false-settlement number. `alerts_tables.py`
   computes them (first, preliminary run in section 3). Still missing: the window start
   (market creation date; the sample does not carry it) and the admission-rule tagging.
   Definitions: a unit claims YES when
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
5. First real alert emails: done on October 6 for five days of mail (the plan's "First
   real alerts" section: 22% of alert results exist in GDELT, alerts arrive a median
   10.7 hours after GDELT's record, no result cap at ten, Content-Type now signed). Still
   to do: the truncation transform for the GDELT units, and a second pull after two weeks
   for the digest shape and the alert-count limit.
6. Run the forward test as pre-registered and report it.
7. Contract work for an alerts market type, after the second pull in step 5 (digest shape
   and the alert-count limit): signer pin on
   `googlealerts-noreply@google.com` and the key hash, outlet host allowlist from the
   result's URL, a body profile for the quoted-printable HTML part. Separately, someone
   must own verifiable execution of the student.

## 7. Open items for the owner

- Rotate both teacher keys, the OpenRouter key and the TypeSafe key in `jev.json`; each
  was pasted in chat once. The OpenRouter daily limit no longer matters.
- Add a Gmail filter so mail from `googlealerts-noreply@google.com` is never sent to Spam
  (Spam is purged after 30 days); this is an account setting, so the owner does it.
- Decide on a dedicated Google account for evidence collection; the alerts currently sit
  on a personal Gmail, which the trust rules say should not be the custodian.
- Approve the forward-test pre-registration before October 25.
- Still owed from research plan v2: Guardian and NYT API keys, a decision on publishing
  paywalled newsletter text. The newsletter mailbox subscriptions were overtaken by the
  alerts track.
