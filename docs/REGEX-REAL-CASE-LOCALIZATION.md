# Why the baseline missed the reporting-permitted case

September 13, 2026. Read-only diagnosis of the Tupac conviction pair in the
completed 60-pair pilot. It does not change the regex, original inputs, labels,
or benchmark score.

The real newsletter puts the victim context in an article headline, then names
the defendant and reports the murder conviction in its adjacent summary. The
summary inserts the defendant's age between his name and the verb.

The generated affirmative pattern requires only whitespace or selected inline
HTML tags between the defendant name and conviction verb. A comma and age break
that condition. Its subsequent murder phrase must also contain the victim's
name in one of a few prescribed constructions. The actual summary relies on the
headline for that context, so removing the age alone would still not match.

Three constructed Python-regex probes localized those restrictions: an explicit
self-contained conviction sentence matches; adding the age makes it miss; and
placing the victim context in a preceding headline also misses. These are
synthetic diagnostic interventions, not new real examples or accuracy data.
No new pattern was selected, and no contract was run by this check.

This supports testing an article-boundary parser and binding the headline to
its own summary before applying typed predicates. It does not justify matching
names and conviction keywords anywhere in the whole newsletter: the same email
also contains a separate Tupac retrospective and an unrelated conviction story.
Any such new procedure needs its own blind generation, real-pair evaluation and
separate cross-story regression tests. The baseline remains frozen.

Private localization artifact SHA-256:
`12cc2c66a7825af0eceb4dfe7646d53be96ccee1aca0b2015fed12bc97951bff`.
Its parent baseline score file, original generation request and complete pattern
are recorded in that artifact. Private newsletter contents are not published.
