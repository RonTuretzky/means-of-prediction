# What the first real-email review establishes

September 13, 2026. This is a model-adjudicated **60-pair development pilot**,
covering 18 newsletters and 33 fact families. It is not a population estimate,
human-validated ground truth, or a completed review of all 161 natural pairs.

## Answerability comes before accuracy

| Disposition under the supplied original terms | Pairs |
|---|---:|
| Required source evidence not contained in the newsletter | 56 |
| Clear UMass result, missing linkage to the specified dated fixture | 2 |
| NFL result clear, intended market year unresolved | 1 |
| Sufficient ordinary reporting branch: Tupac murder conviction | 1 |

The source finding uses a strict, contained-evidence reading: one NYT newsletter
does not establish a required consensus of reporting, and it does not become an
official source merely by reporting the same result. This does not mean that the
reported result is false, or that the market could not settle with additional
evidence. It does not establish how the platform would adjudicate every source
clause. A market designed explicitly around NYT reporting is a different product
and must have a separate benchmark.

The Tupac market expressly permits credible reporting as an alternative to the
court judgment. The September 1 newsletter names Duane Keith Davis and reports
that he “was found guilty of first-degree murder.” The accompanying headline
identifies the Tupac conviction. This supports the ordinary Yes branch before
the December 31 deadline. Appeals need not finish under those terms. We did not
verify whether the email arrived before platform settlement or submit an
on-chain proof in this study.

The UMass newsletter reports a 37–21 win and the 29.5-point underdog status,
but does not date the game. Its two market inputs omit a year. The NFL newsletter
does identify September 9, 2026 through its date and “last night”; the original
four-field market input still omits the intended year. The two reviewers disagree
on whether context is sufficient for that linkage, so it remains unresolved.
Additional public metadata may resolve these issues in a separately versioned
study; it was not silently inserted into this one.

## Baseline results after the label seal

| Existing baseline procedure | Correct on the one answerable pair | Directional/conflicting outputs on 58 insufficient pairs | Execution failures across all 60 |
|---|---:|---:|---:|
| Regex candidate-side detector | 0/1 | 15 | 2 |
| Qwen strict decision | 1/1 | 40 | 5 |
| Qwen strict decision plus exact-quote filter | 1/1 | 28 | 5 |

The one answerable pair comes from **one email and one event family**. Reporting
0% versus 100% as projected accuracy would be misleading. The counts show that
Qwen handled this particular reporting-permitted case and regex abstained.
They do not establish general superiority or a reliable deployment success rate.

The unsupported-output counts are diagnostic signals, not observed on-chain
losses. Regex supplies candidate sides rather than a complete source/time
verifier. Qwen's strict outputs are model decisions, and exact quotation does not
establish source admissibility. The quoted variant removes some unsupported
claims but leaves 28 on this pilot's insufficient-evidence subset. Source-policy
handling therefore needs explicit testing before optimizing extraction recall.

The earlier **63/161 regex factual hits, 75/161 raw Qwen factual answers and
55/161 exact-quote Qwen factual answers remain unchanged**. They answer a different
question and are not replaced by this much smaller conditional pilot.

## Why model agreement is insufficient

All 120 isolated Astra requests completed and passed raw request/response audits.
The two passes agreed on the core label in 60/60 cases and the settlement label
in 59/60; complete condition-state agreement was 48/60. These are correlated
same-model reviews, not independent human judgments.

Root reviewed agreement as well as disagreement. In seven advancement pairs,
one or both passes treated a future USTA-confirmation fallback as a present
standalone prerequisite. Root did not adopt that additional blocker. The
required official-information or reporting-consensus source route remained
unestablished, so their settlement disposition remained insufficient. This is
a concrete reason to review rule branches rather than promote labels by voting.

The study consumed 1,278,172 recorded input tokens and 136,644 output tokens,
with no missing usage records. Frozen prompts, full semantic inputs, service
outputs, exact quote validation and every adjudication remain private. No Qwen
weight training occurred. Labels were sealed before the baseline output join.

Private artifact hashes:

- Raw audit: `749f13b5b35f32a7f66969b66fe89bf9017914025469b7587fcf783bea79d498`
- Adjudicated labels: `f5a89076ae95dc93c0adbac4e7b3725dd525abb8db38d4c8da87811c34c446fa`
- Label seal: `3fdbfd9c9756ff21bba09c58c16b4258d9a7be86beb98f342e09fc7bcba6686f`
- Baseline comparison: `cfd7b6c29ac0814b64b5f48b8a5668ef45f642e77952b5bafcd7b1cc317c5bd0`

## Next experiment

Before another full prompt round, inspect source-condition preservation in
Astra's generated rules and source-condition application in Qwen's outputs.
Evaluate missing market metadata separately from missing email facts. Extend
the review to the remaining natural pairs before claiming corpus coverage.

Keep two tracks explicit: faithful application of existing Polymarket terms,
and new markets whose terms deliberately accept NYT reporting. Test typed
source/time conditions and deterministic arithmetic as new procedures while
preserving both original baselines. Do not relabel source-limited examples as
answerable just to increase the denominator or improve a score.
