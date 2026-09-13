# Research next steps after the real-data review

September 13, 2026. This is a continuation plan, not a launched training run,
production change or measured improvement. Keep the existing regex and Qwen
baselines, raw failures and reserved evaluation data unchanged.

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

## Finish the evidence benchmark before another full optimization round

Complete the exact remaining-pair annotation attempt set, raw-audit every
planned disposition, adjudicate both valid reviews against original terms and
full email, and seal labels before joining the unchanged baseline scores.
Invalid or incomplete dual reviews remain unresolved. Publish the full selected
161-pair accounting, not only the successful annotations or answerable cases.
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
