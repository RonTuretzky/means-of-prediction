# Article expansion checkpoint — September 14, 2026

This phase added a real publisher metadata registry and a separate development
market sample. It did not produce a full-article benchmark or new accuracy scores.

| Artifact | Actual result |
|---|---:|
| Publisher RSS feeds archived | 8 |
| Feed-item occurrences | 215 |
| Distinct article URL identities | 178 |
| Full article bodies | 0 |
| New sampled markets / event groups | 1,000 / 1,000 |
| Markets with lexical candidates | 16 |
| Candidate pairs | 21 |
| Markets retained without candidates | 984 |
| New settlement evaluations / weight-training runs | 0 / 0 |

A lexical candidate is a discovery lead, not verified relevance, answerability
or a successful settlement. The 16/1,000 figure is not coverage or accuracy.
The matcher uses market questions and RSS titles/descriptions only, requiring
at least two shared non-stopwords and retaining the top three TF-IDF cosine
matches per market. It does not use payout labels, market rules or model calls.
Original source occurrences remain privately stored and referenced. For each
identity, the current matcher uses the first sorted record ID as representative.
Review found zero title/description, publication-date or canonical-URL conflicts
among the 33 duplicated identities. A future version should expose the
representative ID and conflict status explicitly.

The feed publication range is September 7–14. Of the 178 identities, 112 have a
representative feed publication timestamp inside the market collection window
(August 29 13:38:08.478 UTC–September 12 13:38:08.478 UTC); 66 are later.
For the 215 occurrences those counts are 118 and 97. Retrieval happened after
the historical settlements. Publication timestamps do not prove that the
captured version was available at market resolution. Later items remain in the
queue as discovery leads and cannot establish earlier availability.

## Reproducible private artifacts

All paths below are under `~/.local/share/means-of-prediction/`:

- `nyt-article-registry-20260913/`: collection plan, eight raw feeds, metadata,
  manifest, and `audit-20260914T0234Z/audit.json` with a collector snapshot.
- `article-market-universe-20260913-v3/`: corrected 1,000-market sample, complete
  eligible IDs, exclusion sources and source-page hashes. Earlier versions are
  preserved intermediates; use v3.
- `nyt-rss-market-retrieval-20260914/`: frozen matching plan, exact code snapshot,
  candidate queue and hashed outputs.

The root independently reconstructed all 215 RSS records, checked artifact
hashes, verified the 1,000 distinct sampled IDs/event groups and exclusion
boundary, and checked the 21-candidate/984-unmatched accounting. Files are private;
article metadata and raw feed content are not checked into Git.

Implementation is in `app/scripts/research/article_collection/` and
`app/scripts/research/articles/`. The three collection/freeze/matching runs are
already complete and refuse to overwrite their directories. Do not rerun their
commands into those destinations. The article importer accepts separately
obtained files; see [its schema and commands](ARTICLE-CORPUS-PIPELINE.md).

## Remaining research work

1. Obtain usable full text from a user-provided local export or an available
   content service. No suitable full-text source or NYT API key was configured.
   Public developer APIs return metadata; blocked article requests must not be
   retried through workarounds.
2. Preserve document provenance, versions, publication precision and retrieval
   time. Review each candidate against the original market's source clauses and
   timing. A single NYT article does not itself establish a reporting consensus.
3. Create an independently reviewed answerability set, retaining insufficient,
   unmatched and unresolved cases. Freeze event-separated evaluation inputs and
   gates before running candidates.
4. Compare story-bound regex and supported Qwen extraction/comparison changes
   against contemporary baselines, including all errors and repeats. Separately
   authored NYT-source markets require a prospective evaluation.

The next model should resume here rather than repeat prompt optimization on the
same email cases. Prior regex/Qwen findings remain unchanged. Luna, Terra and
Sol handled bounded inventory, collection and implementation tasks; this phase
used local deterministic processing instead of new settlement inference.

Validation: five article-importer tests, four market-freezer tests and five
metadata-matcher tests passed. These synthetic software fixtures test pipeline
behavior only; they are not added to the real benchmark.
