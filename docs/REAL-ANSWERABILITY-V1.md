# Real-email answerability review, version 1

Prepared September 13, 2026, after the user approved making real evidence the
primary benchmark. This is a new annotation study, not another prompt revision
and not a retrospective change to the frozen regex or Qwen scores.

## Question

For which existing email–market pairs does the complete email establish a
permitted outcome under the original public rules? Once that subset has been
adjudicated, how often do the existing methods recover the correct outcome,
abstain or choose the wrong side?

The old 161 factual pairs use 18 distinct emails and 33 fact families. The full
development email inventory has 143 documents; these are different denominators.
The 161 factual labels are not strict-settlement sufficiency labels.

## Frozen first panel

Select all 19 pairs passing the old cached-closure timing screen, then fill to
60 by deterministic family round-robin. Selection uses no method scores or old
outcome labels. The 60 pairs cover all 18 emails and all 33 fact families. This
deliberately stratified, exposed development panel is not a representative
sample of all markets or an independent test set. The remaining 101 pairs stay
outside this first review stage.

The timing screen is for sampling only. A market's event deadline is not
automatically the deadline for publication of evidence, and cached closure is
not a verified rule deadline. Annotators do not receive that screen or the
cached resolution outcome.

## Two isolated reviews

Each pair receives two tool-free Astra reviews. Both receive the complete frozen
semantic email and original public terms. Neither receives old factual labels,
generated rules, regex/Qwen outputs, optimizer feedback or the other review.
One review starts from the reported event; the other starts from rule conditions.
They use the same model and are correlated. Agreement is provisional annotation,
not independent human validation or permission to publish a settlement rate.

Each review separately labels the core reported fact and permitted settlement.
Settlement supports A, B, a nonbinary contingency, insufficient evidence or
ambiguous rules. Seven explicit checks cover identity, event, metric, time,
source, finality and exceptions. Quotes are validated against the supplied full
email and original rule text. Missing metadata stays missing. Linked articles
are not included as email evidence. Source restrictions and triggered fallback
branches must be interpreted, not waived or indiscriminately required.

Authentication of the supplied bytes is assumed only for this semantic review.
Cryptographic verification, MIME support, witness size, gas, and a production
settlement attempt remain separate gates. No aggregate of this panel is a live
end-to-end deployment estimate.

## Execution and review

There are 120 frozen jobs, four concurrent requests, high reasoning effort,
no tools and no hard output cap. Known serialized input totals 1,264,096 tokens;
the longest job has 13,737. These are local preflight counts, not billed usage.
The existing transport preserves actual requests, terminal output and usage.
Every job has one attempt. An interrupted or uncertain call is not silently
reissued. Existing hosted usage-stop markers prevent further submissions.

The code, tests, transport helpers, original inputs and each job are hash-bound
in the private plan. Its SHA-256 is
`bf5ae169adbae28b430c516c85b368041e0eb47d70adb7969a7a6df73dd53474`.
Before launch, root reviews the plan and records that hash in a launch artifact.
Eleven focused tests cover blinding, selection, completeness, exact quotes,
unmet conditions, nonbinary outcomes and exclusive attempt markers.

The plan was independently reviewed and launched. The separate
`real_answerability_audit_v1.py` reconciles each saved annotation against the
actual service request, raw response, model identifier, one-attempt lineage,
token usage and recomputed quote/condition validation. Five additional tests
reject changed annotations, extra requests, changed tools and identity swaps.
A complete audit is required before any annotations can be used in adjudication
or scoring; the ordinary annotation summary alone is not this gate.

After both passes, manually adjudicate agreement as well as disagreement using
the complete evidence and original terms. Preserve ambiguous cases explicitly.
Do not choose cases because either method succeeded. Freeze adjudicated labels
before joining old method outputs. Report the full panel, the adjudicated
answerable subset, errors, abstentions and unreviewed cases separately. Show
source and timing blockers rather than folding them into extraction failure.

The separate `real_answerability_score_v1.py` enforces the order: complete raw
audit, explicit disposition of every panel pair, a write-once label seal, then
loading the frozen original baseline outputs. It reports answerable-pair
recovery, wrong sides, conflicts, abstentions and execution failures; an empty
answerable denominator yields an undefined rate, never zero. Counts of distinct
answerable emails and families accompany pair counts. The quote-filtered Qwen
variant remains a separate result, and regex results measure candidate sides,
not a complete source/time verifier. Eight focused scoring tests pass.

Adjudication is performed by a model reviewer and is marked as such. A credible
report, an official result and a consensus requirement are distinct. An email
must contain enough evidence for a permitted branch; a link or unrelated photo
credit does not establish corroboration. A missing calendar year or conflicting
schedule must remain visible rather than being silently filled from old labels.
Do not treat an untriggered fallback as an extra prerequisite for the ordinary
branch. Missing evidence and ambiguous terms are not No outcomes.

This stage does not touch reserved evaluation evidence or launch V4. The earlier
V3 run was interrupted at 1,717 finalized records and remains incomplete pending
reconciliation; no partial V3 quality score is used in this study.

## Commands

From `app/scripts/research/blind`:

```sh
python3 -m unittest test_real_answerability_v1 -v
uv run --python /opt/homebrew/bin/python3 --with tiktoken==0.14.0 python real_answerability_v1.py verify
python3 -m unittest test_real_answerability_audit_v1 -v
python3 real_answerability_audit_v1.py --partial
```

`prepare` already ran and refuses to overwrite the private study. `run` requires
the reviewed launch artifact, preserves an exclusive run marker, and is not a
resume command. `report` only summarizes preserved annotations; it deliberately
does not compute a settlement accuracy against unadjudicated model labels.

The public findings slideshow is available at
[research-results](https://ronturetzky.github.io/means-of-prediction/research-results/).
Its source lives in `app/public/research-results/index.html` and is served by the
repository's existing Pages workflow. Private emails and annotation outputs are
not part of the site.
