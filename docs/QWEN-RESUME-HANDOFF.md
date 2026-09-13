# Qwen research checkpoint and continuation

## Continuation update — 2026-09-13 20:37 UTC

The user subsequently authorized pushing the checkpoint and continuing the
experiment until the usage limit. Commit `7f2b52ba733018013a3fc0e781e280a430a07afa`
was pushed and verified on `mop/checkpoint/qwen-research-2026-09-13`. The earlier
local-only publication restriction below is historical; deployment and live
settlement remain outside this research continuation.

V2 is finished: 1,914 successful judgments and one preserved output-cap failure.
Both root and child independently reconciled all 1,915 raw responses and input
token counts. On 1,754 common completed cases, grounded factual passes fell
55 → 43, strict positive controls fell 446 → 284, and negative false claims fell
14 → 2. V2 fails the paired nonregression gate; baseline remains the provisional
leader. These are development results, not population settlement coverage.

Both frozen probes are also finished and audited. On the selected panel, original
and quote-first each passed 5/6 positive controls with 2/4 negative false claims;
quote-first lost two exact quotes. Separate predicate calls passed 1/6 positives
with 0/4 negative false claims at roughly twice the input cost. Neither procedure
is adopted. Do not rerun the write-once probe commands below.

Hosted Astra capacity became available again without an account change or reset.
The recovery helper preserves the nine prior usage-limit failures and permits a
single new attempt per unfinished feedback job, stopping persistently on any
fresh usage-limit response. All 78 V2 full-body feedback shards are complete.
The direct V3 optimizer packet would exceed the configured context: its known
text/schema count is 448,726 tokens. It is preserved privately. Nine reviewed
second-level summarization jobs cover all 235 earlier lessons and all 12 complete
diagnostic cases with 48 responses. All nine are complete and independently
audited; they consumed 507,031 input and 38,388 output tokens. These summaries
are explicitly lossy abstractions, and the final optimizer retains their complete
lineage. The final V3 packet has 78,498 known input tokens and SHA-256
`feed9abb19de89c1df6c2c7b2d5a9e2706aacd3f9c2370fc23640ce2615fe82e`.
Root approved its exact structural, lineage and context review. The single
optimizer attempt completed, and both resulting prompts were read in full and
approved before rule generation. The generator is 4,856 characters, SHA-256
`8b3d73e41de936283b19b77d1a254f56a13954d130a8973816b41961ca3578ca`;
the judge is 4,927 characters, SHA-256
`38fd8e474870deb938f8c3785e12d3956dffe92ef26ef22d546ae6229004747a`.
This remains the same full-email, single-call, five-field judgment procedure.

V3 local evaluation is now running. A third diagnostic, under
`slides/qwen-basis-probe-20260913`, is frozen and independently reviewed with 16
synthetic tests. It adds a compact entity/value/comparison record before the
original five outputs, without repairing final answers from that record. It
must run only after V3 completion and verified local-model quiescence. Its input
freeze is `570a5243f3622ca3cc3f8fe74103d14f75cf474dc9ace7705b190ab2a35f0436`;
the failed-response reporting amendment is
`8854a9b8ea98a1daf9c25caf76211a2bef221693b937dc810be079c110ab0a13`.
Source-only archival copies are included in `docs/research-checkpoint/basis-probe`.

`qwen_hierarchical_optimizer.py` owns the nine-job summarization and
separate final-optimizer gates. `qwen_guarded_rules.py` prepares a bounded
public-only feeder after exact prompt review, with at most ten requests in
flight and a persistent stop on the first usage-limit error. The exact plan
`431bc0902a70b5bb9b53e78093eaabcb59e338c5417bb2d4b80bf79725f056e5`
and source/runtime-bound `v3-loop-launch-protocol.json` were independently
reviewed. The V3 coordinator PID 86209 launched at 19:45:40 UTC. All 241 rules
succeeded, and all 1,915 full requests passed the token preflight: 6,593,643 input
tokens in total, maximum 16,154 per request. Judge PID 86480 and serial feedback
PID 86481 started at 19:55:15 UTC. At this snapshot, 591 judgments and 25 feedback
shards were complete, with no fresh usage stop. The explicit
`v3-local-released.json` marker
permits root's later diagnostic while remaining remote feedback completes.
Do not run the older eager generation command for V3. Inspect current processes
and private artifacts before resuming; this paragraph is a timestamped snapshot.

A fourth diagnostic, `slides/qwen-crossed-probe-20260913`, crosses baseline/V3
rules and judge prompts on the same twelve old-development cases. Its panel and
cyclic order are frozen, and the code passed independent review and nine tests.
All 48 exact requests were prepared after V3 rule freezing and independently
verified without reading V3 judgments. Its input freeze is
`446cf7feab76dd857050efe9113e1bee7d2bef93b76b264be27c18bcd796a3ea`,
and review SHA-256 is
`9c9120d5cc618280bdfbea0ea062828d8b17e449cbf8551f96e5a8bbaa4c0ec9`.
Actual inference must follow full V3
completion, local release, basis-probe completion and a separate execution gate.
All 48 planned rows remain in reporting, including unavailable rules without
replacement calls. Original baseline and V3 replays help qualify observed
differences. This diagnostic has no automatic selection eligibility. Source-only
copies are archived under `docs/research-checkpoint/crossed-probe`.

The separate dataset task checked NYT intake through 20:00:10 UTC and found no
new messages since the 12:49 snapshot, with no failures. The empty check snapshot
is `nyt-future-data-snapshot-20260913-200000`; root verified its four reported
manifest hashes without reading email contents. Existing reservations remain
unchanged. Root preserved five raw-audited V3 control-error reviews covering twelve cases: unsupported administrative No decisions, numeric comparisons, reversed participant roles, excluded actions and nonbinary deadline outcomes. The child also reviewed five correlated Apple abstentions. These are streaming observations, not aggregate performance or a reason to change frozen inputs.

The future V4–V6 hierarchy helper is independently reviewed, with 15 focused
tests. The future full-round coordinator has 18 focused tests; 92 total Qwen
tests pass. Root independently reran the coordinator tests after reviewing its
failure-stop and in-flight-drain behavior. No future optimizer inputs or calls exist.
Its mandatory audit/selection entry points and complete-review prerequisites are
documented below. A read-only milestone watcher refreshes `PROGRESS.json`; reap it
and all other writers before any selection.

New private root reviews are `v2-and-order-probe-review.private.json` and
`predicate-probe-review.private.json` in `slides/parallel-track-review-20260913`.
All reserved evaluations remain sealed. The remainder of this document preserves
the earlier checkpoint and procedure; completed steps are historical.

## Original checkpoint

Checkpoint requested by the user on 2026-09-13, before further experiment work.
This document supersedes the old no-commit instruction for a **local checkpoint**.
Publishing, deployment, live prompt promotion, and real-email settlement remain on
hold. Commit as the configured user without a co-author trailer.

## Start here

The user wants blind rules generated by **Astra**, settled through two parallel
paths: deterministic regex and local **Qwen3.5-35B-A3B** reading the complete email.
Regex has reached a documented practical plateau. Continue the Qwen experiments
until useful improvements stop, then complete the reserved evaluations. This is
prompt/rule optimization, not model-weight training.

The active repo is `/Users/wk/conductor/workspaces/research/porto-novo`.
The Git remote for this product is `mop` (Means of Prediction); `origin` is the
larger research repository. Do not push to either as part of a local checkpoint.
This tree contains work from multiple earlier sessions; preserve all of it.

The local Qwen process can keep running when the conversational agent stops or
changes model. **Inspect before restarting anything.** At 18:46:09 UTC on Sept 13:

- V2 had 1,743 finished results of 1,915, including one failed control.
- All 241 V2 Astra rules were generated; 58 feedback shards were finished and 61
  had started. These counters are a snapshot, not a completion claim.
- Local judge PID was `24116`, coordinator PID `82681`. Verify command lines as
  well as PIDs; PIDs can be reused.
- The one failed answer reached the 2,048-token output cap: HTTP 200, finish reason
  `length`, unfinished JSON. Keep it failed; do not retry to improve the score.
- No V2 partial accuracy has been used to tune the probes. V2 inputs are fixed.
- No Qwen final selection, order-probe calls, predicate-probe calls, supplemental
  email opening, or original independent fixture opening had occurred.

`PROGRESS.json` is updated independently. Its `completedCalls` includes finished
failures; derive successful counts from each kind's `statuses.completed`.
`driver/v2/judge/completed.json` plus the complete aggregate/summary are the real
completion gate. The coordinator ends at
`two-revisions-complete-awaiting-plateau-review`; it does not select automatically.

## What is already known

| Method | Result | Decision |
|---|---|---|
| Regex baseline vs five revisions | No revision satisfied the selection criteria | Keep baseline; regex run complete |
| Qwen V1 vs baseline, same completed cases | Exact-quote-grounded factual passes 55 → 40; strict positive controls 447 → 383; false claims 14 → 12 | Regression; do not promote V1 |
| Qwen V2 | Full evaluation in progress at checkpoint | Await complete scores and raw-response audit |

V1's full factual denominator was 161: baseline 55 and V1 48 grounded passes, but
baseline had 18 failed rule generations. The same-case 55 → 40 comparison avoids
counting greater API availability as an accuracy improvement. Same-case summed
request time rose about 59%. These development examples are not a random sample
of Polymarket, and retrospective factual reports are not verified timely,
original-rule-admissible settlements. Never present these numbers as the fraction
of all Polymarket markets settleable from NYT mail.

Two reviewed diagnostics are prepared on the same 12 old-development examples:

1. **Order probe:** 24 calls, original output order versus exact quote first.
   Only schema property/required ordering changes; the full rule, email, prompt,
   model and sampling settings are identical. Six pairs start with each variant.
2. **Predicate probe:** 24 additional calls, one A predicate and one B predicate
   per example. Each sees the full six-field original rule and complete email.
   The adapted system prompt/schema are an explicit confound. Verdict-first order
   was fixed before either probe runs. Both NO means NEITHER; both YES means
   CONFLICT/unsettled; an invalid side makes the pair unscorable. This has no
   factual classifier and **cannot qualify under the main selection gate**.

Each probe has six positive and four negative synthetic controls plus two natural
examples. The natural factual labels are not strict-settlement gold. Three
baseball controls share one event. These are selected diagnostic examples, not an
independent accuracy estimate. Neither probe permits automatic adoption.

## Private artifacts and source checkpoints

All paths below are local private storage. Git contains source and procedure
snapshots, not email bodies, credentials, evaluation labels, or model outputs.
The Git checkpoint alone cannot recreate private experimental results. Back up
these directories privately if moving machines; do not upload them to the public
repository or a public issue.

Base: `/Users/wk/.local/share/means-of-prediction/`.

| Relative directory | Purpose |
|---|---|
| `slides/astra-qwen-nyt-round1-20260912` | Main Qwen dataset, immutable requests/responses, rules, feedback, prompts, runtime, progress and reports |
| `slides/astra-nyt-round4-20260912` | Completed regex experiment; keep its independent test out of Qwen training |
| `slides/parallel-track-review-20260913` | Root review notes, offline comparator, baseline/V1 audits and paired reviews |
| `slides/qwen-order-probe-20260913` | Reviewed, frozen order probe; not yet run at checkpoint |
| `slides/qwen-predicate-probe-20260913` | Reviewed, frozen strict-only predicate probe; not yet run at checkpoint |
| `slides/paired-natural-evaluation-20260913` | Prepared supplemental evaluator; adapter not yet frozen |
| `qwen-evaluation-reservation-20260912` | Sealed 12-question/120-fixture independent Qwen evaluation |
| `supplemental-natural-evaluation-20260913-125243` | Sealed two-new-email × 241-question provisional annotations (482 pairs) |

Read `slides/parallel-track-review-20260913/ROOT-REVIEW-STATUS.md` for detailed
decisions and recovery history. It is private. Do not read older dataset-task
conversation turns: they may disclose reserved fixture authoring.

Integrity anchors for recovery (do not open the protected contents just to check
structure; hash the original bytes first):

| Artifact | SHA256 |
|---|---|
| Original Qwen independent fixture file | `238f49b3e43c57e33d1caa6f5a2763b645297118c63b96d0bb334da05d9bbbf0` |
| Original Qwen reservation seal | `2999875a35b5f2938548176bbcf1b73b8b409bdfc29b2058d0a11d23d8cb6f10` |
| Supplemental annotation file | `05493843ac62819edd8698c94e7955d6dcfafef172ba82012a64e9cc89613b1e` |
| Supplemental reservation seal | `0cbba9ed889a299fa72316223422d9f209926cb1f3433f3999d59c010ac85acf` |
| Supplemental evaluator protocol | `298307aeb2d28790bac0acc225c3a76269a150cd081399b594231225f256434e` |
| V2 generator prompt | `6d23deb3885edea10f885c06a937d033d489934338790d85be01c83ef5ccf4d8` |
| V2 judge prompt | `9bb0c7392077b5323ee5739cca3359a33327bdea4a38ccca5ebd07e0f2dca4c4` |

Source-only copies of the probes, evaluator and comparator are under
`docs/research-checkpoint/`, with SHA256 provenance in `source-manifest.json`.
Those copies are archival: executing them in their Git directory changes their
relative artifact roots. Run the original private procedures, whose seals still
bind the original bytes. The main shared harness is committed under
`app/scripts/research/blind/`.

## Model changes and handoff to another assistant

The **coordinator model**, the **Astra generator/teacher**, and the **Qwen judge**
are separate roles. Another assistant model may coordinate this handoff, run
checks, and summarize results without changing either experimental model.

The user specifically requested Astra for continuation. The transport in
`astra_transport.py` explicitly requests `gpt-6-astra` for public-only rule
generation and development feedback/optimization. Do not silently substitute the
coordinator model or supply this conversation/workspace history to a blind rule
generation request. The generator must see only its sealed public input job.
Teacher/optimizer jobs may see the declared development evidence and lessons.

The prior Qwen subagent ended with a Codex usage-limit error around 18:22 UTC;
the independent local Qwen process continued. Local inference does not require
that subagent to remain alive. Verify actual feedback transport results before
assuming the hosted Astra jobs are healthy. Preserve failed/uncertain attempts;
do not mass-retry, consume a reset, change accounts, or change the generator model
without authorization. An authorized future model substitution needs a new named
method, exact model/version/runtime record, fresh public-only rule draws and a
new comparison; it must not overwrite an existing method.

Local runtime is pinned to instance `mop-qwen35b-research` at
`http://127.0.0.1:1234`, model key `qwen3.5-35b-a3b`, Q4_K_M GGUF:

```
f25d609171b8f80950a60f38696597f74025de4070682d2fb1eeffe306ca7d5d
```

Artifact size: 21,169,116,992 bytes. Context 131,072; four local workers; temperature
0; seed 20260912; 2,048 output tokens per call. LM Studio 0.4.1+1, backend
`llama.cpp-mac-arm64-apple-metal-advsimd@2.13.0`; SDK 1.4.0 at the path recorded in
`runtime.json`. The template opens a thinking tag despite the toggle, and baseline
and V1 returned no separate reasoning text. Do not claim reasoning was disabled.
Do not unload unrelated models. This local quantization is not bit-exact GasKiller
int8 execution or a cryptographic settlement proof.

## Resume sequence

### 1. Inspect the live owners and completion artifacts

From the repository root:

```sh
ps -p 82681,24116 -o pid,ppid,stat,etime,command
cat /Users/wk/.local/share/means-of-prediction/slides/astra-qwen-nyt-round1-20260912/PROGRESS.json
cat /Users/wk/.local/share/means-of-prediction/slides/astra-qwen-nyt-round1-20260912/DRIVER-PROGRESS.json
```

Do not invoke `qwen_autorun.py` from scratch: it would collide with write-once
actions. Prior V1 recovery commands are historical and already completed.
If a process died, inspect its `driver/<method>/<phase>/started.json`,
`process.json`, `completed.json`, and `output.log`, plus per-call started/result
records. Reconcile uncertain live requests before any resume. Preserve failed
attempts and source hashes; introduce a documented recovery only for missing work.

### 2. Finish and audit V2; acquire exclusive local inference

Require 1,915 unique V2 aggregate rows, summary, completed driver marker, and no
remaining local judge process before either probe. Remote Astra feedback can
finish concurrently, but no other local model calls may interleave. With the old
subagent unavailable, the new coordinator must verify quiescence directly.

The offline audit does not call a model or open fresh fixtures:

```sh
cd /Users/wk/conductor/workspaces/research/porto-novo/app/scripts/research/blind
python3 -c "import qwen_final_audit as a; print(a.verify_phase('v2', 'development'))"
cd /Users/wk/.local/share/means-of-prediction/slides/parallel-track-review-20260913
python3 compare_methods.py v2
```

Save the audit output privately outside the main Qwen root, without overwriting
an existing audit. `compare_methods.py` refuses overwrite. Run
`qwen_error_transitions.compare('v2')` only after complete scores exist; inspect its
current entry point before invoking it. Compare V2 to baseline on the full cohort
and common completed cases; also compare V1. Do not infer correctness from an
exact quote alone.

### 3. Run the reviewed order probe, then the predicate probe

In each original private probe directory, verify `input-freeze.json` and
`reviewed.json`. Write `run-approved.json` once using the procedure's `once()`
helper, containing the actual timestamp and verified values:

- `inputFreezeSha256`
- `reviewSha256`
- `v2JudgmentsSha256` (complete aggregate)
- `localInferenceQuiescent: true`
- Predicate probe only: `orderSummarySha256` (completed audited order summary)

This is an internal coordination record, not another user-approval request.
Do not write it until the facts are established. Expected input/review hashes:

| Probe | Input freeze SHA256 | Review SHA256 |
|---|---|---|
| Order | `f2bd28bf3876c85fa1bce950fc91620a36c766491eb06fe075c7dd073ddeb84b` | `c86e13a33750d84aa3e1ec9850819df0f33b36e8881ee2cccc6c713aec520ef2` |
| Predicate | `69c713b19920b8c624f4eb21785d15e8dc64159e470b2072e7df6aac66339e77` | `ee5234ce8fd01007bdd78e960e08722c5d3845b3b11607e9e96d78f99022c879` |

Then, separately in each original probe directory:

```sh
python3 probe.py preflight
python3 probe.py run
```

The order helper validates its preserved reporting amendment as well as the
original seal. Keep every raw response and uncertain attempt. Read the full
summary and manually inspect changed decisions. Confirm the requested field order
was actually emitted. Compare contemporaneous original replay to the older
baseline before attributing changes to order. Count the two probes separately in
total usage. Do not start another main iteration until V2 and both diagnostics
have been assessed.

### 4. Decide whether another development method is useful

At least two revisions were required; V2 completion alone does not prove a plateau.
A compact baseline-anchored V3 is a possible next experiment if the long prompts
regress, not an adopted method. Use all declared development feedback, preserve
public-only generation, review exact prompts, freeze inputs, preflight complete
emails, evaluate the full 1,915-row cohort, and retain every failed request.

If adopting a new schema/order/decomposed procedure, add per-method procedure and
wire-schema lineage **before** evaluation. Prompt hashes alone cannot distinguish
property ordering. Existing `judge_request` uses four arguments and a global
schema, and the natural evaluator assumes its combined five-field output. Do not
silently modify global behavior or retroactively recompute old scores.

### 5. Final selection and untouched tests

Quiesce all writers, coordinator processes and status/log writers before selection.
The selection seal covers existing root files except its explicit exclusions;
`DRIVER-PROGRESS.json`, operator-state files and logs can invalidate it. Log
selection output outside the main root. Freeze selected method/runtime/source;
generate and freeze **all 48 new Astra rule draws before opening the original
120 reserved fixtures**. Fresh methods are baseline plus selected nonbaseline;
if baseline stays selected, compare it to the best development challenger.

Use `qwen_guarded_challenge.py` from the selected `sealed-source` directory for
these fresh draws, rather than the older eager `challenge` command. Prepare and
review each exact plan, then run the two selected methods **sequentially**, with
at most four requests in flight globally. The wrapper retains failures, blocks
retries and fixture reads, and refuses to create complete artifacts for a partial
cohort. After both 24-draw cohorts complete, the original `freeze` command performs
the joint 48-draw verification. If the persistent usage stop has fired, keep this
stage pending and the fixtures sealed.

After selection and the 48-draw freeze, freeze the supplemental evaluator adapter
before opening its new email bodies. Run its local model calls only after the
original fresh evaluation's local calls finish. Original directory:
`slides/paired-natural-evaluation-20260913`; phases are:

```sh
python3 evaluate.py freeze
python3 evaluate.py prepare
python3 evaluate.py regex
python3 evaluate.py qwen --method baseline
# Also run the selected Qwen method if different, then:
python3 evaluate.py score
```

Read the current argparse definitions before execution. Score labels only after
all selected predictions finish. There are two new documents, not 482 independent
observations; the 241 questions were already used in development. The 482 labels
are provisional single-author annotations, with 17 ambiguous pairs in either
layer. Do not use this evaluation to retune after opening.

Last, run the prepared metadata restoration diagnostic: original/restored twins
for 28 affected development rows per unique baseline/selected method. It is gated
on final selection, fresh audit and completed supplemental evaluation; it cannot
reselect. Date metadata comes from the signed email Date header, not DKIM `t`.

## Checkpoint validation and limits

### Future V4–V6 hierarchy (reviewed 2026-09-13; not started)

`qwen_future_hierarchy_v1.py` preserves the pinned V3 implementation. Do not
prepare V4 until V3's full local evaluation and feedback are complete and the
order, predicate, basis and crossed probes have completed raw-response and score
audits. Its private directory is `ROOT/future-hierarchy-v1/v4` (then `v5` or `v6`).
Create the reviewed `focus.txt` and `focus-reviewed.json` there first. The review
requires `approved: true`, `focusSha256`, an existing `anchorMethod`,
`v3LocalReleaseSha256`, and `probeSummaryHashes` keyed by all four probe names.
It also requires `probeAuditReviews` under the same names: each entry has `path`,
`sha256`, and `fullRawResponseAndScoreAudit: true`, binding the prior independent
audit. Optional `additionalReviewHashes` maps approved development review paths
to exact hashes. These fields attest to completed reviews, never prospective ones.

From `app/scripts/research/blind`, use the pinned tokenizer with the existing
Python 3.14.6 executable; Python 3.12 fails the archived probe runtime seals:

```sh
mop_future() {
  uv run --python /opt/homebrew/bin/python3 --with tiktoken==0.14.0 python qwen_future_hierarchy_v1.py "$@"
}
mop_future capture --method v4
# Review proposed-job.private.json and proposal-sources.json; write
# proposal-reviewed.json: approved, proposalSha256, sourcesSha256.
mop_future prepare --method v4
# Review all exact shards and token counts; write
# meta-reviewed.json: approved, planSha256.
mop_future meta --method v4
mop_future prepare-final --method v4
# Review final job and preflight; write
# optimizer-reviewed.json: approved, planSha256, jobSha256.
mop_future optimize --method v4
```

Every prior full teacher lesson is covered once, with current fragment manifests
and source hashes. Each probe contributes its same 12 cases and every declared
variant, including unavailable records. Raw responses remain complete and request
factoring reconstructs original content. Snapshot verifies seals, response coverage
and raw hashes; it does **not** independently rederive the previously audited probe
scores. The final optimizer sees explicitly lossy meta summaries. Hosted meta and
optimizer calls are serial, single-attempt and obey the persistent usage stop.
Review the resulting prompts and guarded rule plan separately before any full
development run; this helper does not launch it.

Once a future hierarchical optimizer exists, use `mop_future audit` and
`mop_future select`, including from later coordinators. The scoped dispatcher
retains V3's original verifier, audits V4–V6 independently and rejects unknown
methods. Bare `qwen_round1.py audit` deliberately fails closed for future jobs.
Quiesce every writer before selection and keep selection stdout outside `ROOT`.
After the selected source seal and all evaluation gates, change into
`ROOT/sealed-source` and invoke the same pinned command with `final-audit`.
Finalization rejects unsealed helpers or imported dependencies. Do not run the
old final auditor directly for a study containing these future revisions.

### Future full-round coordinator (reviewed preparation; not launched)

After the future optimizer finishes and both complete prompts receive their exact
`prompt-reviewed-v4.json` gate, prepare the guarded rule requests and the new
`qwen_future_round_v1.py` launch protocol from `app/scripts/research/blind`:

```sh
uv run --python /opt/homebrew/bin/python3 --with tiktoken==0.14.0 python qwen_guarded_rules.py prepare --method v4 --workers 10
uv run --python /opt/homebrew/bin/python3 --with tiktoken==0.14.0 python qwen_future_round_v1.py prepare --method v4
# Root reviews the exact generation plan and full launch protocol before:
uv run --python /opt/homebrew/bin/python3 --with tiktoken==0.14.0 python qwen_future_round_v1.py run --method v4
```

The generation directory's `reviewed.json` requires `approved: true` and
`planSha256`. `ROOT/future-round-v1/v4/reviewed.json` requires `approved: true`,
`protocolSha256`, `localQuiescenceConfirmed: true`, `predecessorCompletionHashes`
matching the protocol, and distinct `retiredProcessIds`. Include every predecessor
stage PID and all retired coordinator/probe/watcher PIDs relevant to local
quiescence. V4 explicitly requires the known V3 coordinator PID **86209**; every
listed PID must actually be dead. V5–V6 additionally verify the prior future
coordinator's completed marker and PID. These are review gates, not autoapprovals.

The protocol captures source snapshots, Python/Node identities, tokenizer,
runtime, optimizer and generation plans, prompts, and predecessor completion
hashes. A global coordinator lock and exclusive launch markers prevent duplicate
owners or implicit restart. The sequence is scoped lineage audit, guarded rules,
raw rule audit, full token preflight, then unchanged four-worker Qwen inference
alongside one-worker full-evidence Astra feedback. An immutable feedback-stop
marker handles a failed judge or invalid full-cohort release: the isolated
feedback worker checks during wait sleeps and around each hosted call, drains any
in-flight request, preserves its artifacts, and sends no next request. Global
`time.sleep` and all pinned V3 sources remain unchanged.

`v4-local-released.json` appears only after successful judge process exit and
complete cohort validation, even while feedback continues. A fresh hosted usage
stop prevents new requests; an already running judge can finish. Final audit uses
the future dispatcher. The coordinator never selects a method, starts another
round, opens reserved data, or launches a probe. Replace `v4` with `v5` or `v6`
only after that method's own preparation and reviews; preserve every failed stage
and reconcile explicitly before any recovery.

Research tests, contract tests and app/script checks are recorded with the final
checkpoint result. Unit tests use synthetic fixtures; they do not reopen sealed
holdouts. A passing build does not certify live deployments, real-email settlement
soundness, production prompt-injection resistance, or the new research procedures.

The completed regex experiment, v9 native fork and original independent test are
preserved privately; do not restart them or copy their fresh labels into Qwen.
The current deployed market path has one affirmative predicate plus deadline NO;
it does not implement the research two-predicate conflict policy.

Suggested opening instruction for a different coordinator model:

> Read docs/QWEN-RESUME-HANDOFF.md and the private ROOT-REVIEW-STATUS.md. Continue
> from the existing immutable artifacts. Inspect live processes before restarting.
> Keep Astra as generator/teacher and the pinned local Qwen as judge. Complete V2,
> audit it, run the reviewed order and strict-only predicate probes in sequence,
> and decide the next useful development method before opening any reserved data.
> Preserve failures, account for all calls, do not publish private email material,
> and do not deploy or promote a live settlement method.
