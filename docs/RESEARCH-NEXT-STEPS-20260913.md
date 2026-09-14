# Research next steps after the real-data review

September 13, 2026. This is a continuation plan, not a launched training run,
production change or measured improvement. Keep the existing regex and Qwen
baselines, raw failures and reserved evaluation data unchanged.

## Disputed-market cohort — September 14

The user also requested a separate all-history dispute index and future training
against it. See [the dispute index](DISPUTED-MARKETS-INDEX-20260914.md) and
[training admission](DISPUTED-MARKETS-TRAINING.md). Index first challenges as well
as escalated disputes, including requests that later settled and those still
unresolved. Report exact source coverage and unresolved market joins; do not
call a current-status filter a complete historical dataset.

Use this as a separately reported challenge cohort for both regex and Qwen.
Preserve observed oracle settlements separately from reviewed factual and
answerability labels. Keep connected markets and repeat requests together,
quarantine prior evaluation overlaps, and admit no case without an evidence and
label review. The proposed 20% cap for reviewed disputed training cases is an
initial configuration, not a measured optimum; evaluation strata stay separate.
This addition does not reopen or modify existing frozen experiments.

## Article expansion update — September 14

See the [article expansion checkpoint](ARTICLE-EXPANSION-20260914.md) for exact
artifacts and the remaining steps. The source preparation phase has advanced. Eight publisher RSS feeds yielded
215 metadata occurrences representing 178 distinct URL identities. Zero full
article bodies were collected. Raw feeds and normalized records were privately
archived and independently reconstructed. See [RSS capture](NYT-RSS-REGISTRY-20260913.md).

A separate 1,000-market development sample is frozen from 422,952 eligible
cached markets, with one market per sampled event and all 253 previously
exposed/reserved IDs excluded. Only the v3 freeze is valid for further work.
See [market inventory](ARTICLE-DATASET-INVENTORY-20260913.md).

The [local article importer](ARTICLE-CORPUS-PIPELINE.md) now preserves API
metadata separately from declared complete or partial article exports. It
retains versions, hashes original and normalized bytes, rejects tampering, and
records unknown publication precision. It does not obtain full text or establish
source admissibility. The RSS registry was collected before the market v3
freeze; this batch is retrospective discovery, not a prospective blind test.

The remaining critical path is unchanged: obtain usable article text, review
source admissibility and answerability against original market terms, separate
event groups, freeze evaluation inputs and gates, then compare both candidate
paths with a contemporary baseline. No new model evaluation or weight training
was launched for this metadata expansion. Earlier accuracy results remain
unchanged. A local export or permitted content service is the missing input;
the public NYT APIs do not supply full bodies. Do not repeat blocked article
requests or replace missing bodies with feed summaries.

## What the completed diagnostics changed

More prompt detail has not reliably improved settlement. The source-check
paragraph reduced unsupported claims in its paired replay but left many intact;
some changes came from quote formatting, and the unchanged baseline itself
varied between runs. A requirement to return no missing conditions is only a
consistency check on the model's own assertions. It cannot establish that those
assertions are true or that the right rule branch was applied.

The regex miss on the reporting-permitted conviction case is more concrete:
an age interrupts the expected name/verb adjacency, and victim context appears
in the headline rather than the adjacent summary. Matching keywords globally
would combine unrelated stories in that same newsletter.

## Completed evidence review; preserve its boundaries

The full selected inventory is now accounted for: one answerable pair, 157
insufficient and three unresolved. See [the completed findings](REAL-ANSWERABILITY-FULL-V1-FINDINGS.md).
The procedure below is complete and must not be rerun as a new attempt set.

The review accounted for every planned annotation, adjudicated valid pairs
against original terms and full email, and sealed labels before joining
unchanged baseline scores.
Invalid or incomplete dual reviews remain unresolved. The published 161-pair accounting retains every disposition.
Retain the original 60-pair result as a separate historical pilot.

Use the new public market captures to prepare a separately versioned input with
explicit market event identifiers, UTC start times and declared time zones.
The NFL year repair is a candidate fixture improvement; it does not retroactively
change the old ambiguous label. UMass still needs evidence linking the email's
reported game to the dated fixture. Record both market metadata and document
availability time. Do not silently import payouts into reader inputs.

## Build useful real positives without changing the question

There are two distinct products to evaluate:

1. Existing Polymarket terms: keep every source restriction and fallback. Collect
   documents that actually satisfy an allowed branch. One publisher reporting an
   outcome is not evidence of reporting consensus by itself.
2. Newly authored NYT-source markets: define this source rule explicitly before
   observing future evidence, generate both rule formats from public terms only,
   and run a prospective paper evaluation. This is a separate benchmark, not a
   relabeling of existing Polymarket markets to raise their scores.

Do not replace missing real positives with synthetic positives in the primary
estimate. Existing synthetic controls remain a separate diagnostic suite.
Freeze the next market universe and observation window before retrieval, retain
markets with no relevant email, and group by event/email rather than counting
related thresholds as independent evidence. Full article collection remains
separate from email evidence; the completed article-access pilot obtained no
article bodies, and its browser fallback was blocked. Do not work around that
block or count links/challenge pages as collected text.

## Test one bounded representation change per path

For regex, prototype headline-to-summary story binding with exact original-text
spans, then deterministic extraction of supported entity/value/operator fields.
Reject cross-story joins and preserve an explicit unsupported result. Keep
synthetic age, negation and cross-story probes separate from all real scores.
The one inspected conviction case is a diagnostic example, not independent
validation for a parser designed after reading it.

For Qwen, separate evidence extraction from a deterministic comparison only in
supported numeric families. Preserve ordinary and fallback branches explicitly;
an unmet fallback is not necessarily an unmet ordinary branch. The source-check
regression that called straight sets an Over-4.5 result motivates this separation.
Exact spans still do not prove correct entity binding or source admissibility.

Freeze candidate schemas, full input representation, all denominators, error and
coverage gates, runtime and the confirmation-repeat procedure before inference.
Compare against a contemporary baseline replay. Count every repeat, failure,
wrong-side answer and conflict; do not pick the most favorable output. No
candidate may be promoted solely for abstaining more often. If the real positive
set remains too small, report that limitation and defer a projected accuracy
claim rather than running another broad prompt search against the same examples.

This work is prompt and program research. A weight fine-tuning phase has not
started and would require a separately defined dataset and evaluation plan.
