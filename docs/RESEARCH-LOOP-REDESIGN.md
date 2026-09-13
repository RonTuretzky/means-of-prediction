# Research loop redesign

Proposed 2026-09-13 after the user requested a strategy review; the user then
approved the direction and requested a real-data primary benchmark. Further full
prompt revisions under the old design remain on hold. Finish and archive
the already frozen V3 run. Its prompts, inputs, scores and output cap stay fixed.
The existing future-round helpers remain available, but no V4 launch is approved
by this document. The design below is a research proposal, not a measured gain or
a production settlement policy.

## What the current results establish

The loop has good request provenance, full-input checks, retained failures,
matched comparisons and reserved evaluations. Preserve those controls.

Five regex revisions did not beat the original baseline; fresh regex testing
recovered no positive cases in the 96-case positive cohort for either tested
method. Qwen's first two completed revisions also failed the paired improvement
gate. V2 reduced unsupported claims while losing valid positive settlements and
grounded natural factual matches. More detailed instructions have not produced
reliable improvement. V3 is unfinished and cannot yet establish a round result.

On 1,389 shared completed synthetic control cases, baseline versus V2 made
446 versus 284 correct claims and 42 versus 26 incorrect claims. Incorrect claims
were 8.61% versus 8.39% of all model settlement claims under the provisional control
labels. This combines wrong-side decisions with false claims on negative cases;
the much smaller negative-only false-positive rate is not the overall error rate.
These are raw directional claims, not verified live settlements; this diagnostic
does not add an exact-quote acceptance filter to the frozen strict scorer.

The existing data mixes natural factual labels, synthetic strict-settlement
labels, weak candidates and unlabeled coverage. Control factual scores compare
against strict labels; administrative outcomes can make that comparison wrong as
a factual target. Exact quotation also does not establish semantic entailment.
Existing raw scores must remain intact, with these limitations made explicit.
The current paired eligibility gate also pools control and natural
`wrongFactualOutcomes`. A new evaluator must gate factual correctness against
independently authored factual labels, rather than strict control outcomes.
Do not retroactively change the original gate or declare an old revision improved:
V2 also regressed on natural factual recall and strict positive recovery.

## 1. Establish what the evidence actually permits

### Use real evidence for the primary benchmark

Synthetic fixtures test rare boundaries, negation, wrong entities and unsupported
claims cheaply. Retain them as a separately reported regression suite, never as
the headline estimate of live settlement performance. Do not manufacture missing
positive examples or combine their denominator with natural evidence.

Build the primary benchmark from actual market terms and resolutions paired
with original NYT evidence. Preserve two evidence tracks: full authenticated
emails, and separately obtained article text. An article linked from an email is
not thereby part of its DKIM-authenticated body. Article performance cannot be
reported as email-contract performance. Inventory accessible full text before
claiming a collected article corpus; metadata and links alone are not full text.

Freeze a market universe and observation window before retrieval, including
markets with no relevant NYT coverage. Preserve original rule versions and
clarifications, resolved outcomes, controlling event deadlines, publication and
receipt times, and the evidence version actually available at the evaluation
time. An event deadline is not automatically an evidence-publication deadline:
apply the original rule's distinction. Later reports may support retrospective
facts while being unavailable to an earlier attempted settlement.

The public resolved outcome labels which side won; it does not label whether
this particular document proves that side. Independently adjudicate sufficiency,
source restrictions and exceptions. Natural unrelated, incomplete, contradictory
and premature reports provide real negative cases. Keep genuinely insufficient
evidence distinct from a market's No outcome.

Report three separate quantities: the fraction of all markets with sufficient
NYT evidence; correct recovery among those answerable markets; and correctness
among all attempted settlements. Also report end-to-end correct coverage over
the full frozen market universe. Count each market once for that coverage metric
and predeclare how multiple emails are combined. Split by event family and time;
keep the existing reserved data sealed until its approved evaluation stage.

### Current real-data measurements, not deployment projections

The existing selected development cohort contains 161 natural factual pairs
across 33 fact families. On the full denominator, counting failures as unrecovered,
the original regex baseline has 63 factual hits (39.1%). The provisional best
completed Qwen method remains its original baseline: 55 correct factual answers
with exact supporting quote presence (34.2%), or 75 correct factual answers
without that quote requirement (46.6%). Quote presence alone does not prove
entailment, source admissibility or correct settlement. Later completed Qwen
revisions have not passed the improvement gate; V3 has no completed result yet.

On the 140 pairs completed by both original baselines, regex has 57 factual hits
(40.7%) and Qwen has 53 quote-grounded factual hits (37.9%). This restricted
comparison excludes failures and must not replace the full-denominator report.
These selected, repeatedly exposed pairs are not a representative sample of all
Polymarket markets. No defensible live strict-settlement success percentage has
yet been established for either path. The new real benchmark must measure it.

Create a separately versioned, independently reviewed diagnostic set from
already exposed development data. Start with approximately 60 diverse
email/market pairs across the available event families, rather than selecting
only errors or many thresholds from one event. Use two blind annotation passes
and adjudicate disagreements against the full email and original public terms.
Do not call agreement between model reviewers independent human validation.

Give each pair separate labels for:

- The core fact reported: A, B, neither, or unresolved conflicting assertions.
- The permitted settlement: A, B, split/Other, insufficient evidence, or ambiguous
  original rules. Separate source, timing, identity and finality blockers.
- Exact supporting spans and the complete sufficient rule branch, if one exists.
- Whether the result would still be known with a perfect reader of this email.

This measures the answerability ceiling. A perfect parser cannot recover a fact
that is absent or waive a mandatory official source. Report factual extraction
recall and strict settlement coverage separately, with unresolved labels visible.
This reviewed development subset remains exposed diagnostic data, not a new
independent validation set. Keep weak/unlabeled rows out of accuracy denominators.
Begin with the 19 natural pairs passing the existing cached timing screen plus
stratified late, source-limited and administrative examples. That timing screen
is not a verified settlement ceiling. Extend the inventory across all 161 natural
pairs before claiming corpus settlement coverage.

Keep two product questions separate: faithful settlement under an existing
Polymarket market's terms, and new markets explicitly designed around NYT
reporting. NYT-specific source rules can make the latter more feasible, but they
must not be substituted into the former to improve benchmark scores.

## 2. Locate failures before optimizing

Use the same cases to test three interfaces independently:

| Interface | Diagnostic input | Question |
|---|---|---|
| Rule generation | Public terms only | Did Astra retain the original conditions and alternatives? |
| Evidence reading | Reviewed rule and full email | Did the reader identify the right entity, value, assertion and source? |
| Decision | Reviewed evidence fields and rule | Did it apply the comparison, time boundary and exception correctly? |

Reviewed intermediate inputs are diagnostic interventions, not deployable inputs
or extra information supplied to a blind generator. Include a strong-model
reader on the small reviewed set as a diagnostic comparator, not as ground truth.
If both readers fail because evidence is insufficient, rewriting Qwen is not the
remedy. If Qwen alone fails clear cases, focus on its representation or examples.

The already frozen 12-case crossed probe can help distinguish rule and judge
prompt effects; the basis probe tests explicit evidence/comparison output. They
must follow V3 local release and remain exploratory. Neither their selection nor
their three related baseball cases support an independent accuracy claim.

## 3. Test simpler representations for both paths

For supported market families, have Astra produce a typed rule describing
entities, metric, operator, threshold, units, time bounds, source conditions and
explicit alternative branches. Preserve unsupported semantics and ambiguity;
never force arbitrary public rules into this schema. Generation still sees only
public terms, never target emails, labels or eventual outcomes.

For regex, test a deterministic compiler from that rule to narrowly supported
extractors/checks. Preserve the existing pure-regex baseline as a separate method.
Require story-local binding and rejection of forecasts, repudiated claims and
unresolved contradictions. A substring matcher cannot claim general semantic
understanding. Numeric parsing, comparisons and dates belong in tested code where
the necessary values can actually be extracted and bound to the right event.

For Qwen, test extraction of quoted evidence, named roles, values and controlling
times before deciding. Let code perform supported arithmetic and comparisons.
Qwen's extraction and semantic judgments can still be wrong; exact spans and
deterministic arithmetic do not authenticate their meaning. Keep missing critical
fields unresolved. This is a new procedure requiring versioned schemas, raw
audits and a complete cohort evaluation, not a silent repair of old verdicts.

## 4. Search candidates economically

Use several bounded candidates and retain complementary successes. Change one
factor at a time initially: rule representation, judge instructions, output
structure, or demonstrations. Try a small number of independently reviewed,
training-only examples that demonstrate entity binding, numeric boundaries,
ordinary versus fallback branches and appropriate abstention. No target-case
lookup tables or evaluation examples may enter generation or judging prompts.

Run candidates first on the reviewed diagnostic set, then a larger stratified
development cohort, and finally the full cohort only for finalists. Freeze each
stage before running it; record all failures and all attempted candidates. Use
all development data across the process without paying for every full email on
every speculative prompt. Sampling and promotion criteria need an explicit
amendment to the current full-round protocol before implementation.
Replay the baseline contemporaneously on the small screen and repeat the
predeclared confirmation subset for finalists: previous local probes showed
some verdict variation despite fixed settings. Preserve all repeats rather than
selecting the most favorable one.

GEPA provides a relevant design for retaining a candidate population and using
execution feedback to propose targeted mutations; its published improvements on
other tasks do not establish a gain here. [GEPA paper](https://arxiv.org/abs/2507.19457)
and [implementation](https://github.com/gepa-ai/gepa).
MIPROv2 supplies another useful pattern: search instructions and demonstrations
on minibatches, then evaluate promising candidates on the full validation set.
[DSPy MIPROv2 documentation](https://dspy.ai/api/optimizers/MIPROv2/).
Adopt the experiment design first; replacing the audited transport with a new
framework is not a prerequisite.

## 5. Make promotion reflect useful, safe coverage

Report wrong accepted settlements, accepted-settlement precision, recall among
answerable cases, abstention on answerable cases, correct abstention on
unanswerable cases, and execution failures separately. Include wrong-side
positive decisions as errors, not just false claims on negative controls.
Retain per-family results and natural versus synthetic denominators.

Choose the error tolerance and minimum useful coverage before candidate search.
Promote only with an explicit error constraint and a demonstrated coverage gain;
lower false-positive counts caused by broad abstention are not sufficient.
No observed errors on a small correlated sample do not prove a safe real-world
error rate. Track full-input cost, latency and matcher gas separately from quality.

Group future splits by email and related event family, with a time-separated
final test. Questions sharing an email, event, price ladder or paraphrase are
not independent observations. Do not reinterpret previously exposed development
examples as unseen validation. The two reserved new emails remain two documents,
not 482 independent tests, and all existing reservations remain sealed.

## Next sequence

1. Complete and audit frozen V3, preserving its cap failure and all raw outputs.
2. Complete the two already frozen diagnostic probes after local release; use
   them only to choose hypotheses.
3. Review the approximately 60-case diagnostic set and label the evidence ceiling.
4. Compare the original baseline with a few controlled candidates: concise
   instructions plus reviewed examples, explicit evidence output, and a narrowly
   supported typed-rule/checked-decision procedure.
5. Advance only candidates meeting the declared error and coverage gates to the
   larger and full development cohorts. Preserve the independent evaluation for
   the selected procedure.

Weight fine-tuning comes after a clean task definition and enough reviewed
training examples. The work so far is prompt/program optimization; it has not
changed Qwen's weights. A new fine-tuning phase would need its own dataset,
runtime, evaluation and resource plan.
