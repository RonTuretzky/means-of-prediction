# Article corpus pipeline

This bounded importer creates a private, local article corpus from files already
obtained by the operator. It performs no network requests, browser automation,
credential discovery or inference. It does not collect any article text by
itself. Obtaining an authorized user or publisher export remains the blocker for
full-text evidence.

Article evidence is stored in its own corpus directory. Do not point this tool at
the DKIM email evidence tree or treat article records as email evidence.

## Commands

Run these commands from the repository root. The output directory should remain
outside the repository; `research-data/` is ignored if a local project path is
needed.

```sh
python3 -m app.scripts.research.articles import-nyt \
  --api archive \
  --retrieved-at 2026-09-13T18:00:00Z \
  --input /path/to/nyt-archive-response.json \
  --corpus /path/to/private-article-corpus

python3 -m app.scripts.research.articles import-nyt \
  --api article-search \
  --retrieved-at 2026-09-13T18:00:00Z \
  --input /path/to/nyt-article-search-response.json \
  --corpus /path/to/private-article-corpus

python3 -m app.scripts.research.articles import-full-text \
  --input /path/to/authorized-export.jsonl \
  --corpus /path/to/private-article-corpus
```

NYT Archive API and Article Search API responses must contain a
`response.docs` array. The importer records `_id` (or `uri`), `web_url`,
`pub_date`, the declared retrieval time and the source kind. `abstract`,
`snippet`, `lead_paragraph` and `headline` values are retained only under
`metadata_fields`. Their record classification is always `metadata_only`, their
`text` field is `null`, and they are never eligible as full text.

## Full-text JSONL schema

Every nonblank line must be one JSON object with all of these fields:

```json
{
  "schema_version": "article-full-text-v1",
  "source_kind": "user_full_text_export",
  "article_id": "publisher-or-export-id",
  "canonical_url": "https://publisher.example/article",
  "publication_date": "2026-09-01T08:00:00-04:00",
  "retrieved_at": "2026-09-13T18:00:00Z",
  "text_completeness": "complete",
  "provenance": {
    "declared_by": "person-or-publisher-making-the-declaration",
    "acquisition_method": "publisher download",
    "source_reference": "receipt-export-id-or-local-reference"
  },
  "text": "Article body supplied in the authorized export."
}
```

`source_kind` must be `user_full_text_export` or
`publisher_full_text_export`. `text_completeness` must be `complete` or
`partial`. A `complete` value makes the record eligible for downstream
full-text use, but the normalized record stores its basis as
`submitter_declaration_unverified`: the importer preserves the declaration and
does not independently prove completeness, rights or authenticity. A `partial`
record remains stored but is not eligible as full text. Missing provenance,
completeness, identity, date, retrieval or text fields reject the whole input
before corpus files are written.

## Storage and integrity

Run one import at a time per corpus; concurrent writers are not supported.

The corpus directory and its `sources/` and `records/` directories use mode
`0700`; files use `0600`. Original input bytes are stored at
`sources/<sha256>.source`. Normalized records point to that hash and include the
zero-based source item position (the physical line position for JSONL), a hash
of the raw item, canonical URL, article ID, publication date, retrieval time,
source kind and evidence classification.

Publication values are preserved exactly as supplied. Each record separately
states whether the value has date or timestamp precision and whether a timestamp
contains timezone information. A date-only value is not expanded into a time or
treated as an exact publication or availability instant.

The manifest is an index and does not repeat article bodies or metadata text.
Those values remain in the private normalized record files and original source
bytes, which lets a low-cost inventory pass avoid loading article content.

Records are write-once and named from the source hash, item position, source
kind and declared retrieval time. An exact re-import is idempotent, while a
later retrieval receipt or a different declared API kind remains a distinct
record. If existing bytes, records or the manifest no
longer match their hashes, the importer stops instead of overwriting them. The
manifest binds each normalized record's canonical bytes with `record_sha256`
and is canonical sorted JSON, so the same inputs produce the same bytes. Imports
with the same canonical URL and evidence
classification retain every occurrence: equal evidence versions link through
`duplicate_of`, while unequal evidence versions set `has_conflict` and list the
other record IDs. No version is silently selected or replaced.

The importer does not establish NYT consensus, article availability time,
market outcomes or source admissibility for any settlement rule. Metadata-only
records cannot answer claims requiring an article body. This module also does
not change the completed email answerability review, frozen inputs, synthetic
diagnostics or prior benchmark results.

## Tests

All checked-in fixtures are marked and named synthetic. Run:

```sh
python3 -m unittest discover \
  -s app/scripts/research/articles/tests \
  -p 'test_*.py'
```
