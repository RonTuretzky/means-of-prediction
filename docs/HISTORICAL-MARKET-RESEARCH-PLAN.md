# Historical market and article research plan

September 14, 2026. This plan separates a public market catalog from evidence
that was actually available, reviewed, and admissible. It does not declare the
catalog exhaustive or launch collection, inference, or training.

## Available records and evidence boundaries

The public holdings provide market metadata and resolution fields for the
existing development inventory and a broader cached market catalog. These are
candidate market records, not reviewed article cases. The provenance inventory
records 241 exposed development markets, 143 original NYT newsletters, 161
market/email pairs, and 33 fact families. The completed answerability review
classified one pair as answerable, 157 insufficient, and three unresolved;
those labels remain tied to the original full email and original terms.

NYT RSS/API-style records may expand URL and publication metadata, but they are
not full article evidence. The article-access pilot obtained zero article
bodies, and the documented browser route was blocked before navigation. A
future authorized export or licensed route must preserve the original bytes,
canonical URL, title, byline, publication date precision, retrieval time, and
version hashes. Feed summaries and challenge pages cannot be substituted for
article text.

Keep three populations distinct: the existing 253 exposed/reserved IDs and
1,000-market article sample/holdouts; the separate 3,879-disputed-question-ID
cohort; and any newly collected historical catalog candidates. Do not join
cohorts by current outcome or admit a disputed record automatically to article
training or evaluation.

## Frozen chronology and grouping

Freeze the market universe, observation window, retrieval cutoff, source
allowlist, and article-version policy before reading article text. Record
market creation, end/settlement, article publication, article update or
correction, and retrieval times as separate fields. Publication date is not an
observation date; an article first published after settlement must not be used
as prospective evidence. Preserve date precision and timezone, and retain all
versions rather than silently replacing an earlier version.

Split by connected event, story, and market family. A repeated threshold,
multiple outcome market, related event slug, or repeated oracle request must
remain in one split. Where an event/story relationship is ambiguous, quarantine
it or place the entire connected component in one split. Grouped splits must be
computed before sampling, review, or model calls.

## Evidence expansion and labels

Full NYT articles can add real positives only when the article's text satisfies
the original market source restriction, timing rule, entity binding, and
answerability requirements. They can also add useful negatives: markets in the
frozen universe for which no admissible article exists by the observation
cutoff, articles with the wrong entity/date, or articles that report a related
fact without satisfying the rule. “No article found” is a coverage observation,
not proof of a negative, until the search scope and cutoff are documented.

Review article text against the original market terms before seeing settlement
outcomes where feasible. Keep oracle outcomes, prices, dispute status, and
later corrections in separate adjudication records; they must not enter the
public judge payload. Require independent evidence review, exact quotations or
spans, source/timing checks, and explicit unresolved/insufficient labels.

The first report should separate (a) available catalog counts, (b) URL/article
availability, (c) reviewed admissible evidence, and (d) outcome agreement.
Report denominators and missingness for each stage. Do not convert a larger
catalog or a larger positive set into a claimed accuracy improvement without a
new frozen evaluation and preserved holdouts.

See `REAL-DATA-PROVENANCE-20260913.md`, `RESEARCH-NEXT-STEPS-20260913.md`,
`ARTICLE-EXPANSION-20260914.md`, and `DISPUTED-MARKETS-INDEX-20260914.md` for
current inventories, restrictions, and separate-cohort handling.
