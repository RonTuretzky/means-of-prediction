# Historical market catalog

This offline catalog unions every market row in the available local public
captures. It is the master inventory, not a claim that the captures contain
every Polymarket market ever created and not a training or evaluation dataset.
Catalog membership, present status, settlement prices, and observed outcomes do
not become truth labels automatically.

The initial inputs are every JSON page under `polymarket-pages/` except its
manifest, four partial/review files under `nyt/`, and every saved market response
from the development provenance repair. The Gamma keyset listing was reachable
with HTTP 200 on September 14, but the unfiltered/default capture represents the
endpoint's default/open surface rather than verified all-history coverage. A
separate explicit `closed=true` capture and cursor-chain audit are required.
Both completed raw-page directories may be added with repeated `--api-pages`
arguments before the single final union run. The builder makes no network
requests and performs no LLM inference.

## Build

```sh
python3 -m app.scripts.research.catalog \
  --pages ~/.local/share/means-of-prediction/polymarket-pages \
  --nyt ~/.local/share/means-of-prediction/nyt \
  --repair ~/.local/share/means-of-prediction/development-provenance-repair-20260913T222520Z/responses/markets \
  --api-pages ~/.local/share/means-of-prediction/historical-market-all-api-20260914/raw-pages \
  --api-pages ~/.local/share/means-of-prediction/historical-market-closed-api-20260914/raw-pages \
  --reserved ~/.local/share/means-of-prediction/qwen-evaluation-reservation-20260912/provenance/excluded-market-ids.json \
  --article-sample ~/.local/share/means-of-prediction/article-market-universe-20260913-v3/sampled-public-inputs.json \
  --output ~/.local/share/means-of-prediction/historical-market-catalog-20260914
```

The output directory is write-once with mode `0700`; files use `0600`.
An `--api-pages` collection must have a sibling `manifest.json` marked
`complete: true`; that manifest and every compressed raw page are hash-bound.
The builder independently replays request logs, raw/stored hashes, partition
flags, and cursor chains. Unaccounted gaps fail the build. One repeated request
in the first open capture is retained as duplicate provenance; the audit reports
its original occurrence counter discrepancy (+100 saved rows) explicitly.
`catalog.sqlite3` contains:

- `sources`: exact input path, kind, byte length, SHA-256, and row count;
- `versions`: every occurrence, market ID, source/row reference, canonical raw
  row hash, public `questionID`/condition ID and event-group ID array when
  present, question, rules, ordered labels, and private `state_json`;
- `markets`: version counts, distinct raw-version counts, judge-field conflict
  names, reserved/article-sample holdout flags, and projection eligibility;
- `rejections`: source references and hashes for rows lacking a market ID.

No first source wins. A market is projected only when all observed non-null
question, rules, and ordered-label values each have one unique value. Any
disagreement is recorded in `conflict_fields_json`, sets `source_conflict`, and
prevents automatic projection. Missing fields also prevent projection. Raw
versions remain addressable through their source file hash and row reference.

`candidate-public.jsonl` is a terms-only projection with `marketId`, `question`,
`rules`, ordered `outcomeLabels`, and `trainingHoldout`. It excludes observed
outcomes, payout vectors, settlement prices, current/historical status, and
open/closed flags. The private SQLite state retains all known state fields
without filtering by open, closed, unresolved, disputed, or resolved status.

The 253 reserved IDs and the new 1,000-market article sample stay in the master
catalog and receive explicit holdout flags. They must not enter training. Usable
evidence cases require a later, separately reviewed admission process. The
disputed-market cohort remains a separate reference and is neither joined nor
modified here.

## Offline dispute mapping

After the final catalog exists, the separate mapper can join the dispute union
by audited public Gamma `questionID`:

```sh
python3 -m app.scripts.research.catalog.map_disputes \
  --catalog-dir ~/.local/share/means-of-prediction/historical-market-catalog-20260914 \
  --dispute-dir ~/.local/share/means-of-prediction/disputed-markets-20260914-union-v3 \
  --output ~/.local/share/means-of-prediction/dispute-catalog-map-20260914
```

The private mapping preserves every dispute event and matching catalog source
version, including event-group IDs, source path/hash/row, raw-version hash,
public terms, holdout/conflict flags, and private state observations. It emits
unmatched question IDs separately and reports distinct question and market ID
counts. It does not select a payout, resolve public-term conflicts, modify the
dispute cohort, read sealed evaluation fixtures, or admit training cases.

Run the synthetic tests with:

```sh
python3 -m unittest discover \
  -s app/scripts/research/catalog/tests \
  -p 'test_*.py'
```

## September 14 background run and handoff

The uncapped open/default and explicit closed collectors are running. This is
an in-progress expansion, not a completed all-history claim. The closed scan
has already reached records created in October 2020. Deleted/private records
are not guaranteed by the public API, and a live keyset scan is not an atomic
snapshot of a moving market inventory.

A detached local `finalize_when_ready` process waits for both complete
manifests, audits them, builds the union with all existing cached rows, and
creates the separate dispute mapping. It runs no LLM calls and admits no new
training cases. Its code is frozen under the private run directory, so later
repository edits do not change the running plan.

Private paths under `~/.local/share/means-of-prediction/`:

- `historical-market-all-api-20260914/`: original **open/default** capture,
  despite its legacy name; see its immutable `scope-correction.json`.
- `historical-market-closed-api-20260914/`: explicit `closed=true` capture.
- `historical-catalog-expansion-run-20260914/`: frozen source, launch plan,
  supervisor output, and `state.json` updated every 30 seconds while collecting.
- `historical-market-catalog-20260914/`: final union, created after both scans.
- `dispute-catalog-map-20260914/`: subsequent separate private mapping.

The run state transitions from `waiting_for_collection` to
`auditing_and_building_catalog`, `mapping_separate_disputed_cohort`, and
`complete`; errors become `needs_attention` with a failure phase. A completed
catalog still has evidence pending. Review the state and collector checkpoints
before any continuation; never start a second writer on an active capture.
The first legacy collector's source remains frozen inside its private capture;
new collections should use `collect_partition.py` with explicit `--closed`.

To start a new capture in a **new** output directory:

```sh
python3 -m pip install -r app/scripts/research/catalog/requirements.txt
python3 -m app.scripts.research.catalog.collect_partition \
  --closed true --output /path/to/new-private-closed-capture
```

The strict collector uses a single-writer lock, opaque cursor pagination, raw
response hashes, and checkpoint replay. It honors `Retry-After` and stops on
403/401; it does not use alternative routes. Resume only a compatible incomplete
strict capture with `--resume` after checking its failure receipt and confirming
that its previous writer exited. Raw data stays out of Git.
