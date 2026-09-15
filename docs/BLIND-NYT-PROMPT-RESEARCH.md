# NYT-specific blind rule generation

The research runner improves the prompt used to generate email-body outcome
regexes. It uses Astra and learns from NYT training emails and actual match
results. This is prompt optimization; it does not train new model weights.

The experiment is private, under
`~/.local/share/means-of-prediction/slides/astra-blind-20260910/`.
Raw mail, evidence excerpts, generated rules, model responses and result files
must remain there. The old `blind-regex-20260910` benchmark stays immutable.
No research result authorizes automatic settlement or public email submission.

## Data boundary

The 149 retrospectively reviewed factual-match cases are grouped by underlying
event and shared raw email, then split into 104 training, 19 validation and 26
test cases. These represent only 5, 3 and 3 independent groups respectively.
The large correlated US Open component belongs to training. This is a prompt
holdout within a selected corpus, not random Polymarket coverage or an externally
pristine test set. Its rate must never be described as the percentage of all
Polymarket markets that NYT can settle.

The initial validation methods each scored 0/19. Following the user's request
to learn from email results, those 19 cases were explicitly released for
calibration, bringing the development pool to 123. Preserve the earlier results;
later scores on those cases are training performance, not unseen validation.
`calibration-release.json` records the change and its timing.

The optimizer and supervised example teacher may inspect development evidence,
outcomes and failures. The 26 final-test cases stay hidden until the selected
method and all final generations have been frozen. Shared raw emails and known
fact families remain grouped; broader news-cycle correlations can still exist.

For a new market, generation receives only its public question, original rules,
outcome labels and ID, plus the frozen prompt and an independent trial number.
A blind review pass can also see its own candidate and syntax errors. It receives
no target email or settled result. One measured arm adds sorted public contender
names from archived public questions, with no payout, prices or closure fields.
That retrospective enrichment is different from the four-field baseline.
Independently authored synthetic controls are
derived from public rules; test controls are not fed into prompt optimization.

## Completed September 12 run

The selected calibrated prompt used medium Astra reasoning and 8,000-token
guidance, with no hard output cap. Two blind review passes reduced pooled
development hits from 18/31 to 15/31 and 14/31, without improving available
negative controls, so the unreviewed generation method was frozen.

All 178 final generations and their raw transport sources were sealed before
test scoring. The 26-market holdout scored **15/78 factual text hits (19.2%)**,
covering seven markets in at least one draw. The original ten-market replication
scored 53/100 but overlaps development. The holdout had 12 synthetic negative
false positives, 12 unscorable negative checks and 24 draws without controls.
Every factual hit was late relative to the recorded closure proxy.

All 68 factual hits fit an encoded witness of at most 4 KiB. Native local calls
at 16 million gas matched four original-benchmark witnesses and **zero holdout
witnesses**. These measurements do not establish deployable settlement rules.
The selected prompt is available through the private generation command; the
browser generator and live settlement worker were not switched to it.

The private `REPORT.md` contains exact regexes, source passages, per-market and
group results, known and unavailable token usage, counterexamples, and gas
checks. Keep the holdout frozen: any revision informed by these failures needs
a new test set to support a fresh unseen-performance claim.

## Model and token accounting

> **Update 2026-09-14:** new generations use Claude Fable 5.1 through
> `app/scripts/research/blind/fable_transport.py`; see
> `docs/FABLE-GENERATOR-TRANSPORT.md`. The Astra transport described below
> produced every completed round and remains in place for their reconciliation.

`app/scripts/research/blind/astra_transport.py` uses the installed Codex sign-in
as an isolated, tool-free model transport. A capability-protected loopback
adapter replaces all incoming workspace/history context with an audited
request. It forwards authentication only to the original OpenAI host, never
stores headers, and exposes no model tools. This is a local research transport,
not a production application API.

The authenticated service rejects `max_output_tokens`. Therefore the previous
2,000-token cap is removed; 4K/8K/16K/32K targets are guidance, not enforced caps.
The experiment compares supported Astra reasoning efforts and review passes.
Actual service-reported output and reasoning tokens are recorded. Guidance,
reasoning effort, visible regex size and actual token consumption are different
measurements. A method's cost includes every generation and review call.
Max-effort pilot calls ended without completion after approximately 902 seconds;
their token consumption is unavailable, not zero. Higher effort is not assumed
to improve recall. Quota failures and explicit recovery calls remain separate
attempts in the audit trail.

Completed streaming output is reconstructed from output-item events, with the
saved client completion as a compatibility fallback. A completed terminal
response may have an empty output array. The first pilot log misclassified that
transport representation as invalid JSON; corrected scoring reuses the original
responses and never regenerates them. Incomplete responses remain failures.

## Evaluation

Report these separately:

- Valid pair, clean known-email factual hit, miss, conflict, wrong outcome,
  search timeout and failed generation, retaining every attempted generation.
- Independent positive and negative controls, including forecasts, negation,
  wrong entity/date/round/metric and nearby unrelated reporting.
- Whether the known email arrived by the market's recorded closure.
- Whether the exact matched source has a valid encoded witness of at most
  4,096 bytes and the full body meets its 192 KiB limit.
- Actual read-only local `RegexLib` validation and matcher gas calls. A call
  failing at the gas limit is not automatically a syntax error. Matcher gas
  excludes DKIM/RSA, storage, body processing and settlement.
- Other full-archive matches as unreviewed candidates, not automatically
  correct results or false positives.

A correct factual passage alone does not establish every original resolution
condition. Official-source, consensus, event-edition and deadline requirements
remain relevant. The body regex also cannot generally reject arbitrary quoted
or denied versions of an otherwise matching substring; selected source windows
can lose the context that would disqualify a statement. The research must report
this limitation rather than silently treating textual recall as safe settlement.

## Run and resume

Run from the repository root with Python 3, the `regex` package and the installed
Codex CLI available. Each model request saves its job, exact unauthenticated
request body, process identity, terminal events, output and usage in its own
private directory. Completed calls are reused. A live or ambiguously interrupted
call must be reconciled before starting another attempt.

```sh
python3 -m unittest discover -s app/scripts/research/blind -p 'test_*.py' -v
python3 app/scripts/research/blind/experiment.py pilot --workers 3
python3 app/scripts/research/blind/improve.py controls --workers 2
python3 app/scripts/research/blind/improve.py optimize --method prompt-v1 --previous prompt-v0.txt
python3 app/scripts/research/blind/improve.py batch --method prompt-v1 --split train --panel --workers 6
```

The sealed private `protocol.json` controls revisions, selection and final
replication. Its latest amendment explicitly permits NYT training feedback.
Do not reset a split, overwrite the old benchmark, or use test misses for another
revision under the same test label. The current app's browser model is a separate
integration; this runner does not silently switch live markets or the onchain
judge to Astra.

After selection, `finalize.py freeze` requires 100 fresh original-benchmark
attempts and 78 final-test attempts (three draws for each of 26 markets).
It seals both generated records and the raw transport sources used by scoring.
`finalize.py score` checks those hashes before reading test evidence. Original
benchmark markets overlap development; repeated draws do not add independent
news events.

`pnpm research:nyt-rule <public-market.json> <private-output-directory>`
(from `app/`) uses the frozen prompt and settings for another market. It rejects extra input fields,
records model identity and all review-call usage, and produces a candidate with
settlement authorization explicitly false. The selected public roster snapshot
only covers its archived markets; a new market may receive no roster enrichment.

## Continued training, round two

`app/scripts/research/blind/round2.py` keeps the continuation in a separate
private directory, `~/.local/share/means-of-prediction/slides/astra-nyt-round2-20260912/`.
The former test cases are now explicitly development data. The first round's
frozen files, prompts and scores remain unchanged.

The development pool contains 161 cases, with a 38-case comparison panel.
Two Astra prompt revisions learn from actual misses, independent development
controls and native execution costs. Sixteen other public questions and ten
newer, training-disjoint emails form a separate challenge. Those candidates
include incomplete topical evidence; this challenge is not a known-positive
recall sample. Its controls are authored using public rules alone and never
enter prompt training. The coordinator saw some of these newsletter contents
during earlier research, so describe this as a retrospective model-input holdout,
not a pristine prospective evaluation.

Before new-email scoring, freeze the method and all challenge generations.
The runner checks public inputs, prompt settings, raw model output sources and
email hashes. It rejects further training after selection. Native checks use
read-only local state overrides; no deployment or public email submission occurs.

The separate `round2_matcher.py` corrects a scoring bug that mistook an optional
escaped plus sign for a lazy quantifier. This correction was checked against
native Solidity, and both baseline and revision outputs are rescored without
regeneration. Original scoring records are retained separately.

```sh
python3 app/scripts/research/blind/round2.py batch --method baseline --workers 6
python3 app/scripts/research/blind/round2.py native --method baseline
python3 app/scripts/research/blind/round2.py optimize --method distilled-v1 --previous baseline
python3 app/scripts/research/blind/round2.py batch --method distilled-v1 --workers 6
python3 app/scripts/research/blind/round2.py native --method distilled-v1
python3 app/scripts/research/blind/round2.py boundary-ablation --method distilled-v1
python3 app/scripts/research/blind/round2.py native --method distilled-v1-boundaries
python3 app/scripts/research/blind/round2.py optimize --method distilled-v2 --previous distilled-v1
python3 app/scripts/research/blind/round2.py batch --method distilled-v2 --workers 6
python3 app/scripts/research/blind/round2.py native --method distilled-v2
python3 app/scripts/research/blind/round2.py boundary-ablation --method distilled-v2
python3 app/scripts/research/blind/round2.py native --method distilled-v2-boundaries
python3 app/scripts/research/blind/round2.py controls
python3 app/scripts/research/blind/round2.py select
# Run baseline and selection.json's bestChallenger on --split holdout --trials 2, then:
python3 app/scripts/research/blind/round2.py freeze
python3 app/scripts/research/blind/round2.py score-challenge
# Run native --split holdout for both methods and independently review the matches.
python3 app/scripts/research/blind/round2.py report
```

These are resumable research commands, not permission to retrain after inspecting
the fresh challenge or to replace the live settlement policy automatically.

### Round-two completed measurements (September 12)

Neither revision beat the baseline under the selection rule fixed before the
fresh challenge. The baseline matched 13/38 known development facts; the first
revision matched 6/38 and the second 8/38. The second revision gained five cases
and lost ten relative to baseline. It learned unemployment and CPI phrasing,
but those numerical witnesses still failed the native matcher at 16M gas.
Available negative controls passed on four baseline factual hits versus two
for each revision; 25/38 development cases lacked controls and do not count as
passing them. The deterministic boundary repair improved syntax without adding
factual hits. The first revision and its repaired version tied on the predefined
ranking fields; method order selected the raw first revision as challenger.

The 64 challenge draws were frozen before scoring ten new emails: 32 baseline
and 32 first-revision draws over 16 public questions. Both produced zero email
matches. Baseline had 32/32 valid pairs; the challenger had 14/32. Neither passed
any of its 128 independent positive-control checks. Baseline incorrectly matched
two price forecasts out of 192 negative checks; the challenger had no observed
false positives but 108/192 unscorable negative checks. Its zero is therefore
not a safety result. Native validation passed for both dialect-valid patterns
in 2/32 baseline draws and 10/32 challenger draws; zero fresh witnesses were
available to execute.

The fresh challenge included incomplete Apple announcement/price evidence,
an undated Lowell hurricane reference, and four topical decoy families. It is
not a known-positive recall benchmark and does not measure coverage of all
settled markets. Manual review did not confirm fully admissible standalone
email evidence for these exact rules. The original 15/78 result remains unchanged.

The run completed 184 model requests: 114 development draws, 64 challenge draws,
two optimizers and four independent control-author requests. Known usage was
2,237,960 input tokens (1,239,936 cached) and 322,955 output tokens, with no missing
usage records. Repaired variants reused existing outputs and added no model calls.

The private round directory contains `REPORT.md`, all exact predicates and source
passages, the two generation/input seals, `challenge-review.private.json` and the
usage audit. The live app and worker retain their previous configuration. No
commit, push, deployment or automatic settlement was performed. Any further
training must use a new experiment directory and a new evaluation set; these
challenge results are now known.

## Continued loop: round three

`app/scripts/research/blind/round3.py` preserves the full baseline demonstrations
and trains two successive addenda from development errors. Its private directory
is `~/.local/share/means-of-prediction/slides/astra-nyt-round3-20260912/`.

The comparison reruns the baseline and both revisions on the same 38 factual
cases plus eight synthetic diagnostics from the now-released round-two test.
An eligible revision must preserve factual hits and positive-control passes
without increasing false positives or invalid pairs, with at least one strict
improvement. A fixed combined score selects among eligible methods; native
factual matches and output tokens break ties. A failed/invalid negative is not
treated as safe rejection. Native artifact consistency is checked across methods.

Twelve other public questions, excluded from all earlier market sets, receive
independently authored balanced synthetic tests. The authors see public rules
alone. Freeze baseline and selected-challenger outputs (two draws per market)
before reading/scoring those fixtures. This challenge tests new wording and
questions, not fresh NYT-email recall. Related event families and repeated draws
remain correlated.

One newly synced NYT email is reserved by raw hash outside training. Its body
is only scored after the same generation seal, using the public questions already
chosen before mailbox sync. This supplemental retrieval check is not a
known-positive recall set or a prospective arrival-after-freeze test.

The runner supports `prepare`, `author`, `batch`, `native`, `optimize`, `select`,
`freeze`, `score-test`, `score-mail`, and `report`. Development is closed after
selection. All original round-one and round-two artifacts remain unchanged;
no live prompt promotion or settlement is authorized by a research score.

During development, the second revision gained a single optional syntax-repair
pass. It triggers only on compiler errors and receives public rules, the existing
candidate and those errors. It never receives email or control feedback. Raw and
effective outputs are retained, both calls are counted, and the final freeze
audits every repair input/output. The v2 comparison therefore measures a prompt
plus repair workflow. This change was fixed before any final-test generation.

### Round-three completed measurements (September 12)

Retaining the demonstrations improved development recall, but neither revision
qualified for promotion. The fresh baseline matched 14/38 known factual cases,
the first revision 11/38 and the second 23/38. The second revision preserved all
14 baseline hits and added nine. Positive-control passes were 6/84, 3/84 and
13/84, respectively. Negative false positives were 5/126, 0/126 and 8/126; the
first revision also had 12 unscorable negative checks from two invalid pairs.
Twenty-five factual cases lacked controls. Development counts remain lexical
detections, not admissible settlement rates.

The frozen independent challenge compared baseline with the second revision on
12 public questions, two draws each. Positive checks improved from 2/96 to 11/96,
covering two versus seven distinct positive fixtures out of 48. The challenger
incorrectly accepted one of 144 negative checks: Karina reaching 74 mph one
minute after the market cutoff. Baseline had zero observed false positives,
with six unscorable negatives and four unscorable positives because one Apple
generation suffered a transport failure. That failed draw was retained without
resampling; the remaining 23 baseline outputs and all 24 challenger outputs
compiled. The comparisons include correlated draws and related event families.

Manual review found no clear label errors in the 120 fictional fixtures. The
synthetic tests assume the facts asserted by their prose; they do not authenticate
sources or establish how often NYT reporting will contain those facts. All 23
challenger development witnesses and all 11 synthetic positive witnesses failed
the native matcher at 16M gas; baseline's 14 and two witnesses also failed.
Positive/negative execution sentinels passed. RSA/DKIM verification, body storage
and transaction overhead are additional costs, excluded from this measurement.

Seven compiler-feedback repairs were retained and audited: five development and
two test calls. Six changed grouping only; one repaired a malformed placeholder
into a literal question-mark pattern that supplied no meaningful Yes detector.
Compiler validity must not be confused with semantic correctness.

The newly synced On Politics digest contained no qualifying evidence for these
12 selected questions in manual review, and both methods returned zero matches.
That single email is not a known-positive recall sample. It was held out of
model inputs and read after generation freezing, but had arrived before the
freeze, so this is not a prospective arrival-after-freeze test.

The round attempted 199 model calls: 138 development draws, 48 challenge draws,
two optimizers, four fixture-author calls and seven syntax repairs. Of these,
198 completed; one transport failure supplied no usage. Recorded usage is
4,742,630 input tokens (1,898,240 cached) and 408,835 output tokens, excluding
unknown usage for that failed request.

Private artifacts include `REPORT.md`, `NEW-DETECTIONS.md` with exact predicates
for the nine added detections, `challenge-failures.private.json`, the frozen
source/input/output hashes, manual review and usage accounting. Further learning
must use a new round and an untouched evaluation set. No live prompt change,
commit, push, deployment or automatic settlement was performed.

## All-data continuation: round four

`app/scripts/research/blind/round4.py` expands optimization and evaluation to
all 161 existing labeled cases across 33 factual events, all 620 available
synthetic fixtures, all 143 archived NYT bodies and 803 historical generated
candidates. Its private directory is
`~/.local/share/means-of-prediction/slides/astra-nyt-round4-20260912/`.
All earlier test sets are explicitly released to development. Eight audited
lesson shards include every email ID and historical output, and the
optimizer receives all shard lessons, all labeled facts/public rules and all
available controls. A later provenance audit found142 of143 original teacher
texts were URL/footer-cleaned, while scoring used complete decoded HTML/main
parts. The earlier inputs remain preserved. A32-batch supplement before
full-v5 supplies every full HTML/main part and full stored mailparser text,
with exact request and coverage audits. Unlabeled emails teach language and
structure only.

Every method covers 189 public markets, scores all labeled pairs and available
controls, and scans all 143 bodies. Newly retrieved unlabeled matches are saved
for adjudication and never counted as known facts or settlement outcomes.
The comparison reports both total hits and mean recall across the 33 factual
events, preventing a single story's many related markets from dominating the
headline result. The older 38-case panel remains a secondary comparison.

The fixed baseline reuses 108 prior calls with exactly matching public inputs,
prompt and settings, selected deterministically before learning without using
their scores. The remaining 81 public inputs are generated once. Reused usage
is separated from newly incurred model calls; failed calls are retained without
result-dependent resampling. Comparisons on this old material remain development
results, not a fresh randomized trial. Each revision receives one optional
public-only compiler-feedback repair, with both raw and effective outputs saved.

Successive revisions learn from the full-data errors. Utility combines mean
factual-event recall, synthetic positive recall, a threefold false-positive
penalty and invalid-pair rate. Promotion eligibility separately requires no
regression in factual hits, positive controls, false positives, invalid pairs
or wrong/conflicting outcomes, with a strict improvement. Native execution is
measured separately and still gates any settlement claim. At least two revisions
are planned; repeated failures to improve guide a plateau assessment rather than
unlimited resampling. No development score authorizes deployment.

A user-requested separate thread, “Expand Means of Prediction evidence dataset,”
owns dataset expansion and a sealed 12-question independent evaluation. It sees
no round-four prompts or generated outputs. The coordinator receives public rules
and provenance first, then freezes method selection and all test generations
before reading any evaluation fixture. The new questions broaden event families;
fictional fixtures cannot estimate natural-email recall. The mailbox expansion
sync found no new NYT messages. Neither thread changes live prompts, commits,
publishes, deploys or submits public email evidence.

The expanded development pass adds 49 public questions with 82 weak natural
pairs, then three more questions with nine contextual pairs. Each method now
generates rules for 241 public questions and scans all 143 archived bodies.
These 91 pairs are evidence cautions, not extra positive gold. The retrieval
queue of more than a million market/email links is unreviewed and is not counted
as a million training examples.

Public-rule-only authors supplied 900 supplemental synthetic fixtures across
90 previously uncovered questions. Together with the original 620, this gives
1,520 development fixtures over 152 questions; 37 primary questions still lack
a usable balanced control set. Author refusals and incomplete outputs remain
recorded. The new controls require human review. From full-v4, bounded teacher
batches include every available fixture and all 241 outputs from every completed
method exactly once. The earlier eight shards retain the original cleaned-text
and historical candidate feedback; the full-body supplement corrects their
body-content coverage claim.

Selection additionally requires no regression on supplemental controls and no
known fatal semantic defect, no loss of event-balanced recall, and strictly
higher utility than the baseline. Full-v2 emitted a player-name pattern without a
result predicate. Full-v3s emitted a bare `NO` alternative matching every email
for one question. Both methods are disqualified; their raw results are retained.
Another gate compares only questions where both candidate and baseline produced
valid completed outputs, so transport or syntax recovery alone cannot count as
a semantic improvement. The prior champion's replication is also disqualified
because one affirmative expression contains an unrelated `dummy` alternative;
a minimal counterexample matches in both the host scorer and Solidity. Failed
benchmark calls are never replaced. Explicit
identical-input recoveries apply only to teacher analysis, in separate artifacts
with all attempts included in usage accounting.

Only 19 of the 161 labeled pairs have email receipt by the cached market-closure
proxy. That proxy is not independently verified resolution time. Retrospective
fact detection, timely evidence, satisfaction of original market rules and
native contract execution are separate measurements. The current contract
checks one affirmative predicate and later permits deadline-based NO; it does
not implement the research scorer's two-outcome conflict check. A selected body
witness cannot prove that no denial appears elsewhere in the full email.

An independent private RegexLib experiment reached 61 of 63 baseline lexical
witnesses within 16M matcher gas, compared with zero using the original artifact.
Its selected version passed 31 unit, differential and fuzz tests. The patch is
unapplied, relies on the measured compiler layout, and excludes RSA/DKIM, storage
and settlement overhead. This is execution improvement, not evidence that 61
markets can settle. The private round directory contains `ENGINE-EXPERIMENT.md`,
the version comparison and patch. Production source and artifacts were not
modified by this experiment.

The Astra prose / local Qwen3.5-35B-A3B experiment has its own worker, model
setup, selection and separate sealed 12-question evaluation. The regex path
does not wait for its download, inference, optimization or label opening. Both
can compare the same 161 factual development pairs and 1,520 controls; their
separate fresh tests are not a matched head-to-head comparison. See
[QWEN-BLIND-RULE-RESEARCH.md](QWEN-BLIND-RULE-RESEARCH.md) for that experiment.

### Round-four development decision (September 13)

The baseline remains selected. Five revised prompts and a replication of the
previous champion produced no candidate that passed all predeclared eligibility
checks. The round is frozen before opening its independent fixtures. The highest
utility challenger without a separately confirmed fatal branch is full-v1;
testing that challenger does not promote it.

| Method | Factual hits /161 | Event macro recall | Positive controls /608 | Negative false positives /912 |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 63 | 32.7% | 42 | 13 |
| full-v1 | 0 | 0.0% | 6 | 2 |
| full-v2 | 52 | 24.0% | 35 | 13 |
| full-v3s | 20 | 3.1% | 26 | 11 |
| full-v4 | 17 | 2.1% | 23 | 8 |
| Previous champion replication | 95 | 53.4% | 85 | 32 |
| full-v5 | 29 | 9.1% | 21 | 6 |

These control columns combine the original and supplemental fixtures. Invalid
or unavailable cases remain in the denominators and are not safe rejections.
The private report lists their counts separately. In full-v5, Astra's service
usage limit caused 60 failed raw generations across all 241 questions and four
additional failed syntax repairs. Those attempts are preserved. On the primary
questions where both baseline and full-v5 completed with usable predicates,
full-v5 still scored fewer factual hits (28 versus 37) and fewer positive
controls (20 versus 26), with fewer false positives (5 versus 8).

This is a practical stopping point for the current regex prompt architecture
and data, not a claim of a global optimum. Additional prompt wording has not
solved the demonstrated surrounding-denial and event-edition limitations.
The private v9 native engine also matches a constructed headline explicitly
described as fabricated, confirming that lower matcher gas does not repair
assertion scope. Qwen optimization continues independently.

### Round-four independent result (September 13)

All 48 fresh generations completed and were frozen before importing the
independent 120 fictional fixtures. With two draws per question, both the
baseline and full-v1 recognized **0/96 positive checks**. The baseline falsely
matched **3/144 negative checks**, versus zero for full-v1. The three errors
were a pardon explicitly before market creation, a fabricated fastest-lap
quotation and a qualifying-session fastest lap instead of a race result.

The original native engine left every positive check unscorable, along with
134 baseline and 138 challenger negative checks. The private v9 engine scored
all 240 checks per method within separate 16M-gas budgets for each A/B call,
reproducing every host match result. This demonstrates improved execution, not
improved rule accuracy or transaction-level feasibility.

An initial native-input hash check rejected a JSON-reserialized fixture copy.
The separately documented recovery used the original sealed source bytes;
parsed fixtures, labels, frozen code, model outputs and engine artifacts stayed
identical. No failed generation was replaced. All prior snapshots and actual
model requests passed the final audit.

No prompt or settlement policy was promoted. These small synthetic tests remain
subject to human review and cannot estimate the percentage of real Polymarket
markets that NYT emails could settle. The private `REPORT.md`,
`independent-evaluation-audit.json` and `PARALLEL-BASELINE-COMPARISON.md` preserve
the measurements and their denominators.
