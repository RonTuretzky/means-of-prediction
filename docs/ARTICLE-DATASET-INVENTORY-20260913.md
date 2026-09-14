# Public article and market dataset inventory

Inventory date: 2026-09-13. This is an offline inventory only. Raw email bodies,
article response bodies, and frozen/private evaluation trees were not read or
modified.

## Market corpus available for reuse

The strongest reusable public records are the current Polymarket API captures
in:

`~/.local/share/means-of-prediction/development-provenance-repair-20260913T222520Z/`

- `baseline-public-markets.json`: 189 market records, one JSON object per
  market. Public fields include `marketId`, `question`, `rules`, ordered
  `outcomeLabels`, `publicUrl`, question/rules hashes, and a `resolution`
  object containing creation/closure times, condition/question IDs, final
  one-hot payout vector, winner, and API-level provenance flags.
- `request-universe.json`: the frozen 189 IDs and associated event slugs used
  by the repair; `marketCount` is 189.
- `public-link-inventory.json`: 1,056 link occurrences from market/event
  response surfaces, 27 unique URLs. These are source/context links, not
  article captures.
- `manifest.v1.json`, `request-log.jsonl`, `comparisons/*.json`, and
  `aggregate.json`: request/response hashes, retrieval metadata, and
  old/new field comparisons. The bounded collection fetched 189 markets and
  55 events from 2026-09-13 22:25:20 through 22:26:23 UTC; all 189 market
  responses succeeded and matched stored question/rules/labels and winners.

The earlier public market caches in `~/.local/share/means-of-prediction/nyt/`
are broader but partial, with a common record shape:
`id`, `question`, `description`, `slug`, `url`, `resolutionSource`,
`outcomes`, `outcome`, `createdAt`, `endDate`, `closedAt`, `volume`, and
`timeBasis`.

| File | Records | Created range | End-date range | Closed range |
|---|---:|---|---|---|
| `topic-markets-partial.json` | 449 | 2025-11-25 through 2026-09-09 | 2026-08-08 through 2027-01-01 | 2026-09-01 through 2026-09-09 |
| `other-markets-partial.jsonl` | 110,391 | 2025-09-22 through 2026-09-09 | 2026-05-31 through 2028-01-01 | 2026-09-01 through 2026-09-09 |
| `residual-markets-partial.jsonl` | 16,343 | 2025-09-22 through 2026-09-09 | 2026-05-31 through 2028-01-01 | 2026-09-01 through 2026-09-09 |

The JSONL counts include the headerless records; all inspected records have a
non-null outcome. The corpus is a discovery/reference corpus, not a complete
platform census and not an evidence-labeled article dataset.

The broadest existing public market table is the paginated cache at
`~/.local/share/means-of-prediction/polymarket-pages/`: 4,289 JSON pages,
428,900 scanned rows, and 423,200 normalized two-outcome markets in the
completed manifest. Its recorded window is 2026-08-29 13:38:08.478 UTC through
2026-09-12 13:38:08.478 UTC. Each page has `markets` and `next_cursor`; market
rows include `id`, `question`, `description`, `slug`, `outcomes`,
`outcomePrices`, `createdAt`, `endDate`, `closedTime`, `closed`,
`automaticallyResolved`, `umaResolutionStatus`, `volume`, `volumeNum`, and
`events`. The manifest is marked `complete` and `publicPaginationComplete`.
This is a frozen historical cache, not a claim about current platform coverage.

`app/scripts/research/article_collection/freeze_markets.py` freezes the
article-development universe offline. Use only the corrected v3 output:
`~/.local/share/means-of-prediction/article-market-universe-20260913-v3/`.
Earlier v1 and v2 directories are preserved intermediate artifacts and must not
be used for evaluation.

The v3 manifest records 428,900 scanned rows and unique IDs, 428,812 markets in
the exact UTC closure window, 88 outside it, 248 in-window exclusions, 5,612
rejected settlement shapes, and 422,952 eligible markets in 78,953 event groups.
The deterministic seed `article-universe-v3-20260913` selects 1,000 event groups
and one market per group. All 241 exposed development IDs and both reservation
lists are excluded; the full exclusion union contains 253 IDs.

The freezer detects conflicting ID versions before eligibility, retaining exact
page references and hashes. It requires `closed` to be boolean true and two
ordered labels with one-hot API prices. Rows with multiple explicit events are
excluded. Unknown events are grouped by market ID and flagged. This particular
capture had zero conflicting IDs, invalid closure times, false/unknown closure
flags, multiple-event rows or missing event groups.

The sample preserves separate `endDate`, `gameStartTime`, `eventStartTime` and
explicit timezone fields. It contains public questions, rules and ordered
labels; winners and settlement prices are withheld from reader inputs. The
manifest pins all source pages, collector code, sample, eligible IDs and
exclusion sources. Output files use mode 0600 and the directory 0700. Root
verification confirmed the sample hashes, 1,000 unique IDs/event groups and
absence of excluded IDs. This is an offline discovery sample from historical
API records, not an independently verified platform census or a labeled
article benchmark.

## NYT URL/metadata inventory

`~/.local/share/means-of-prediction/article-access-pilot-20260913T223148Z/article-manifest.v1.private.json`
contains exactly 20 selected NYT links. Each record has an opaque `pilotId`,
publisher/access fields, redirect and terminal-response references, request
count, retrieval timestamp, and a `selectionReference` with lexical topic,
newsletter date, week band, and hashes. Article fields are `title`,
`canonicalUrl`, `originalPublishedAt`, `publicationMetadataSource`,
`articleWordCount`, and text/hash paths. All 20 records have:

- access status `blocked_http_403_challenge`;
- three GET requests each (60 total);
- null title, canonical URL, publication date/source, and article word count;
- `fullTextVerified: false`, with gaps for blocked access and unavailable
  metadata.

The selection spans 20 newsletter dates from 2026-08-16 through 2026-09-12
(five coarse lexical topic groups). The manifest preserves link identity and
access outcomes only; it contributes zero article texts. The public pilot
summary is `outputs/article-access-pilot-20260913.md` in the prior dataset
workspace. Do not count tracking-link occurrences as articles.

The real-data inventory confirms 143 source newsletters (2026-08-16 through
2026-09-12), 10,518 tracking-link occurrences, 7,919 distinct tracking hrefs,
and zero independently captured full NYT article documents. Those email
holdings remain source evidence and are outside this public article inventory.

## Collector code and credential-variable check

Reusable collectors are:

- `work/provenance-repair/collect.py`: captures public Gamma market/event
  responses, writes `baseline-public-markets.json`, `request-universe.json`,
  comparisons, link inventory, manifest, and seal artifacts.
- `app/scripts/research/nyt-candidates.mjs`: builds the local NYT candidate
  index/SQLite coverage database from cached public market records.
- `app/scripts/research/sync-nyt.mjs`: authorized local mailbox synchronizer;
  it is for newsletter evidence, not article retrieval.
- `work/article-access-pilot/select.py`, `fetch.py`, `fetch-resume.py`, and
  `finalize.py`: the bounded article URL access workflow. It must not be used
  to bypass the recorded site-safety/access restriction.

No NYT article API credential variable is configured in the inspected project
scripts/configs. The only relevant access variables are mailbox variables in
`app/scripts/mailbox.mjs`: `MOP_MAIL_CONFIG`, `IMAP_HOST`, `GMAIL_USER`,
`GMAIL_APP_PASSWORD`, and `IMAP_ACCESS_TOKEN`, plus saved OAuth field names.
These names were checked without reading values. The public market collector
uses unauthenticated Gamma endpoints. `PRIVATE_KEY`, `RPC_OVERRIDE`, and
`GK_API_KEY` are deployment/judging variables and are unrelated to article
collection.

## Frozen-universe selection

For a broader development market universe, create a new versioned public input
from the partial market corpus, freeze the exact ID list, observation window,
timezone policy, event grouping, and treatment of multiple thresholds before
retrieval or evaluation. Exclude every ID in the reserved registries before
selection, using only their metadata/count summaries and ID lists. The complete
exposed development ID source is:

- `~/.local/share/means-of-prediction/slides/astra-qwen-nyt-round1-20260912/public-inputs.json`
  (241 IDs: 189 prior + 49 expansion + 3 follow-up).

The complete reserved ID source is:

- `~/.local/share/means-of-prediction/qwen-evaluation-reservation-20260912/provenance/excluded-market-ids.json`
  (`all`: 253 = the 241 development IDs plus 12 regex holdout IDs).
- `~/.local/share/means-of-prediction/dataset-expansion-followup-20260912-2054/provenance/excluded-market-ids.json`
  (`all`: 250, an earlier reservation snapshot).

Therefore exclude all 241 development IDs when claiming novelty; excluding
only the 189 repair IDs would leak the earlier 52 separately captured markets.
Keep markets with no matching newsletter and
retain their public metadata. A safe next collection uses a new destination
directory and the existing `collect.py` pattern, records the API retrieval
time and source URL, and writes a new manifest; it must not overwrite a frozen
directory or import payouts as reader evidence.

No network collection, inference, evaluation launch, commit, or private-tree
mutation was performed for this inventory.
