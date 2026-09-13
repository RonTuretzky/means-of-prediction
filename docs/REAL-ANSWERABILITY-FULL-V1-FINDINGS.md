# Strict answerability across all 161 existing real pairs

Completed September 13, 2026. The full selected development inventory contains
**one answerable pair, 157 insufficient-evidence pairs and three unresolved
pairs** under the original four-field market inputs and strict contained-email
interpretation. This is not a representative sample of all Polymarket markets,
a human-validated gold set or a projected production accuracy rate.

The answerable pair remains the Tupac conviction market (3709179), whose ordinary
resolution branch permits credible reporting. The email explicitly reports the
relevant conviction. The original Qwen baseline recovers it; regex misses it.
**Qwen 1/1 and regex 0/1 describe one email and one event. They do not establish
100% or 0% expected accuracy.** No live market was settled by this experiment.

## What limits the evidence

| Disposition | Pairs |
| --- | ---: |
| Insufficient: required source evidence absent, sometimes with additional gaps | 154 |
| Insufficient: UMass game-date linkage absent, with no source restriction | 3 |
| Answerable under an expressly permitted reporting route | 1 |
| Unresolved: original NFL fixture year ambiguity | 1 |
| Unresolved: one invalid quotation in each pair's dual review | 2 |
| Total | 161 |

A NYT report of an outcome does not itself demonstrate an official-source result
or reporting consensus. This interpretation does not assert that the reported
fact is false or that Polymarket cannot settle with other evidence. Article links
are not their contents, and neither is a substitute for the email body. The
completed article-access pilot collected zero full article bodies.

The three UMass rules lack a year in their original inputs; the email reports a
37–21 result but does not date that game. New public fixture metadata has since
been captured, but it is a separate future input version and does not supply an
email-side game date. The original NFL ambiguity and all earlier labels remain
unchanged. Two NH-01 Democratic nomination pairs (704170 and 704171) remain
unresolved because one review per pair failed exact-quote validation; their
apparently plausible conclusions were not substituted for a valid dual review.

## Unchanged baselines against the sealed labels

| Method | Correct / 1 answerable | Claims on 157 insufficient pairs | Execution failures / 161 |
| --- | ---: | ---: | ---: |
| Regex candidate detector | 0 | 60 | 3 |
| Qwen strict direction | 1 | 110 | 18 |
| Qwen strict direction with exact quote | 1 | 80 | 18 |

Claims count directional or conflicting outputs. An execution failure is not a
successful abstention; the full denominators retain failures. Three unresolved
labels are kept outside the answerable/insufficient correctness groups. Regex is
a candidate detector, not a complete source/time verifier; these candidate hits
must not be interpreted as completed on-chain settlements. Quote filtering is a
stricter view of the same Qwen outputs, not another model.

The earlier factual-recovery results remain unchanged: regex 63/161 (39.1%),
Qwen 75/161 (46.6%), and Qwen with exact quote 55/161 (34.2%). Those scores answer
a different question and use the original factual labels. The new source-check
prompt was tested only on the separate 60-pair pilot; its 26/53 unsupported
quoted claims must not replace the full-inventory baseline numbers above.

## Review and corrections

The original 60-pair pilot remains preserved verbatim. The exact complementary
101 pairs received two isolated Astra reviews each, using original public terms
and complete semantic emails, with no baseline predictions, payout labels,
linked-page contents or prior annotations in the requests. All 202 requests are
accounted for: 200 valid annotations and two invalid exact quotations; 99 pairs
therefore qualified for semantic adjudication. There were no retries or usage
stops. Actual extension usage was 1,943,429 input and 224,048 output tokens.

Root model adjudication considered every original rule, the 14 complete emails
(already read in the pilot), and both reviews' rationales and condition states.
It also reread the full UMass and Gauff emails. Ninety-nine valid pairs were
adjudicated insufficient; two stayed unresolved. Dual-review agreement is
correlated model annotation, not independent human validation.

Nine positive-advancement pairs repeated an error in both annotations: they
turned a September 27 USTA confirmation fallback into an extra requirement for
settling now. Adjudication removes that freestanding present requirement while
retaining the independently missing official/consensus source evidence. A separate
review of all ten affected tennis rules and four complete emails agreed. The
Alcaraz elimination rule permits early No without waiting for the final or that
fallback deadline, but still requires an allowed source.

The Gauff–Andreeva newsletter item names the players and reports a win without
identifying the US Open or dating the tennis match; its French Open reference
describes Andreeva as champion. The specific target fixture is not established.
This correction is recorded in the new review; it does not overwrite the old
factual benchmark. Agreement on abstention does not establish correct reasoning.

Labels were sealed before the combined scorer loaded unchanged predictions.
The union is exactly 161 unique pairs, with the original 60 labels preserved.
The full raw gate verifies all 202 dispositions and original dependency hashes;
failed annotations remain unresolved. An independent reconstruction of raw Qwen outputs, frozen regex matches and
all denominators agreed with every aggregate. The separate scorer has seven focused
tests for coverage, incomplete reviews, quotes and unchanged-baseline joins.

## Reproduction and next work

See [the extension protocol](REAL-ANSWERABILITY-REMAINING-V1.md),
[the original pilot](REAL-ANSWERABILITY-V1-FINDINGS.md),
[the source-check comparison](QWEN-SOURCE-CHECK-V1.md),
[the consistency diagnostic](QWEN-CONSISTENCY-DIAGNOSTIC.md), and
[the next research steps](RESEARCH-NEXT-STEPS-20260913.md).
Code is in `app/scripts/research/answerability/combined_v1.py`; the run and labels
are write-once private artifacts. Do not rerun inference or overwrite scores.

No candidate is promoted. More real positives satisfying the actual source
rules—and event metadata that identifies the fixture—are needed before another
broad optimization round can support an accuracy claim. Newly authored markets
that explicitly use NYT reporting are a separate prospective product/benchmark;
they must not replace the terms of existing Polymarket cases.

Private artifact SHA-256 values:

- Full extension raw audit: `32c01acf1a24a901c3d8fdabb7b1336bbfabfc3a477c95936a9d76b0c6211ce5`
- New101 adjudicated dispositions: `32bd48488b024bb0f81357f1d6efd0c724efd342ce33f1372715c4b1746ec876`
- Root review record: `3bf528806c824c844c7875c36cf9a859c51969b7a4d21a7b8fdd1c7ad5f1db7d`
- Independent fallback review: `b9baa9d988dd25a55397ae5da670051df5f102ef01246fa5dbb246e51f2ac646`
- Combined label seal: `f126a28f522f27249c63915ff45432a83ac4f64a4e22a82203a8f969f85b5362`
- Independent combined raw/label/score audit: `6b8bac459d845efc58b4e2e2701da7a466d65b7a77f2427f1798357f3e60781f`
- Combined baseline comparison: `8fd94f8b11559d74668594f9324a70d0f840cceb0110a6295a8198fb1ecb8676`

Private emails, raw judgments and annotations are not published.
