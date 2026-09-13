# Exact quote and empty missing-conditions diagnostic

Completed September 13, 2026. This CPU-only diagnostic reuses existing outputs;
it changes no prompts, labels, original scores, contracts, or deployment. No
method or acceptance policy is promoted.

The fixed rule retains a valid directional A/B answer only when its nonempty
quote occurs exactly in the complete semantic email and `missingConditions`
equals `[]`. Otherwise that direction becomes an abstention. Unavailable rules
and failed calls remain unscorable. Conflicts remain separately reported
conflicts and are never accepted directional answers. No factual-agreement
condition, whitespace normalization, source lookup, or semantic repair is added.

The parent specified the rule before aggregate computation. The reviewer had
already read missing-condition lists on selected source-check disagreements and
had seen a related baseline-control diagnostic. This is an analysis of exposed
development data, not a blind or independent evaluation.

## Results

The real-email panel has 60 pairs: one adjudicated answerable pair, 58 reviewed
as insufficient, and one unresolved. Five unavailable baseline rules affect
each variant, leaving 55 executed pairs and 53 executed insufficient pairs.
All 110 paired local calls completed. Both variants retain the single answerable
Tupac case under every gate; that denominator cannot establish general recall.

| Unsupported directions on the 53 completed insufficient pairs | Raw | Exact quote | Exact quote and empty missing conditions |
|---|---:|---:|---:|
| Contemporary baseline replay | 41 | 32 | 25 |
| Source-check prompt | 36 | 26 | 13 |

The baseline synthetic cohort contains all 1,520 controls: 608 positives and
912 negatives. Of these, 556 positives and 834 negatives completed; 130
unavailable-rule rows remain failures and receive no safe-rejection credit.
The source-check prompt was not run on this synthetic cohort.

| Baseline synthetic result | Raw | Exact quote | Exact quote and empty missing conditions |
|---|---:|---:|---:|
| Correct positive directions / 608 total, 556 completed | 447 | 441 | 428 |
| Negative false claims / 912 total, 834 completed | 14 | 14 | 6 |
| Wrong-side directions on positive controls | 28 | 28 | 27 |
| Abstentions on positive controls | 81 | 87 | 101 |

There were no conflicting outputs in these scored cohorts. Compared with the
raw baseline, the combined gate removes eight negative false claims and 19
correct positives, while removing only one of 28 wrong-side answers. It is a
rejection tradeoff, not a solution to incorrect numerical or entity reasoning.

## Interpretation and verification

An exact quote proves substring presence, not entailment or the required source
authority. An empty self-reported missing list does not prove that every rule
condition was checked. A nonempty list can describe an unmet alternate branch
while the chosen branch qualifies, so the gate can reject legitimate results.
The synthetic labels describe stipulated strict settlement outcomes; they are
not independent factual gold. The real pairs share emails and events and contain
only one answerable example.

Eight focused tests cover exact quotes, empty versus nonempty missing lists,
alternate-branch rejection, conflicts, unavailable rows, and distinct positive
and wrong-side accounting. The full original baseline raw-response audit was
recomputed, and all source-check artifacts were checked against the independent
110-response audit before the gate was applied. Original inputs and results
remain unchanged.

The exact source, tests, protocol, and aggregate-only results are archived in
[`research-checkpoint/consistency-diagnostic`](research-checkpoint/consistency-diagnostic).
No raw emails, individual predictions, or private annotations are included.
The archive manifest records the active private directory. The original script
uses its own location to find inputs, so the copy is archival rather than a
relocatable executable; do not run its main function from the archive.

Protocol SHA-256:
`eb6150b53ecc083ecee2a275e765de3b6a5f4666047b9e28c6d5f8f3ee6ae8fa`.
Complete private result SHA-256:
`7210ebbfbf2efa1cd6fd5af9613c68ae35514f16906e37a8a72a6ee188e1e913`.
