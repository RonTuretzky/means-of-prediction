# Disputed-market cohort and training admission

This pipeline prepares a separate, review-gated cohort of markets with dispute
evidence. It does not collect network data, infer disputes from present status,
admit truth labels, modify existing runs, or launch training. The completed preparation run is described in
[the index report](DISPUTED-MARKETS-INDEX-20260914.md): all 3,879 candidate
question groups remain quarantined pending mapping, with zero training admissions.

## Evidence tiers

- `event_confirmed`: a normalized oracle event with chain ID, oracle address,
  transaction hash, log index, requester, identifier, timestamp, ancillary data,
  and nonempty source references. The event is deduplicated by
  `(chainId, oracleAddress, transactionHash, logIndex)`. Conflicting versions of
  the same event key are quarantined.
- `api_history_only`: a Gamma record whose `umaResolutionStatuses` or
  `umaResolutionStatusHistory` explicitly contains `disputed`. This tier is
  reported separately and does not claim on-chain confirmation.
- `unknown`: no affirmative event or API-history evidence. A current `resolved`
  status never proves that a dispute did not occur. Unknown records are retained
  in quarantine and do not enter judge inputs.

All non-quarantined records start with `admission: evidence_pending` and
`labelReview: required`. Private payout or resolution fields are stored only as
observations with `outcomeUse: private_observation_not_truth_gold`.

## Normalized inputs

Oracle event JSONL uses this shape. Optional IDs must remain null until an
audited join establishes them; a hash derived from ancillary data is not a
market `questionId`.

```json
{
  "chainId": "1",
  "oracleAddress": "0x...",
  "transactionHash": "0x...",
  "logIndex": 7,
  "requester": "0x...",
  "identifier": "ASSERT_TRUTH",
  "timestamp": "2026-09-01T00:00:00Z",
  "ancillaryData": "0x...",
  "questionId": null,
  "conditionId": null,
  "marketId": null,
  "sourceRefs": [{"kind": "rpc-log", "ref": "bounded-scan-reference"}],
  "lifecycle": {"eventName": "DisputePrice", "blockNumber": 123, "removed": false}
}
```

Gamma JSONL may include `marketId`, `conditionId`, `questionId`, `question`,
`rules`, ordered public `outcomeLabels`, `slug`, nonempty `sourceRefs`, and the
status/history fields above.
Current status alone is not negative evidence. Each input file and every raw
line is SHA-256 bound in the private admission records and manifest.
When a Gamma row with unknown status is connected to affirmative event evidence,
its reviewed public question, rules, and ordered labels may supply the judge
packet without upgrading the Gamma row's evidence tier. An unknown Gamma row by
itself never enters the cohort.

## Command

```sh
python3 -m app.scripts.research.disputes \
  --events /path/to/normalized-oracle-events.jsonl \
  --gamma /path/to/normalized-gamma-history.jsonl \
  --exclude-ids /path/to/development-market-ids.json \
  --exclude-ids /path/to/reserved-market-ids.json \
  --exclude-ids ~/.local/share/means-of-prediction/article-market-universe-20260913-v3/sampled-public-inputs.json \
  --output /path/to/new-private-dispute-cohort
```

Exclusion files are read only and may be an ID list, a list of market objects,
or an object with an `all` ID list. Any optional market/question/condition ID
overlap quarantines the whole connected group before splitting. Oracle request
keys omit round timestamps, and transitive links across request, market,
question, and condition IDs keep repeated rounds and joined records together.
The remaining records are assigned by connected group to deterministic 80/10/10
train/dev/test splits for both regex and Qwen work. Unmapped event records stay
in the private `mapping_pending` quarantine. A source-verification block records
whether the event came from an indexed subgraph and whether an RPC receipt was
separately verified; normalized event fields alone do not claim RPC verification.

`public-judge-inputs.json` contains only cohort ID, split, optional public IDs,
question, rules, and ordered outcome labels needed for answer mapping. A packet
without question, rules, and labels is quarantined as ineligible. It contains no
dispute tier, lifecycle, status, resolved outcome, price, provenance, or
article/email evidence. `private-admission.json` contains
the evidence audit trail. `quarantine.json` reports conflicts, prior-ID overlap,
and unknown evidence. The manifest hashes every output and reports tiers and
splits separately.

`curriculum.json` is disabled by default. After independent evidence and label review,
it proposes a maximum 20 percent disputed-case share for both regex and Qwen;
this is a configuration default, not a measured optimum. Hard cases target
false positives, ambiguity, and source timing. Dev/test metrics remain separate,
and no final payout becomes truth gold automatically. With zero reviewed rows,
reviewed training admission remains explicitly zero.

Run the synthetic unit tests with:

```sh
python3 -m unittest discover \
  -s app/scripts/research/disputes/tests \
  -p 'test_*.py'
```

Review can follow the existing independent annotation/adjudication protocol;
it is a dataset-quality step, not a request for separate user approval.
Ambiguous or unresolved labels stay excluded from supervised optimization.

Explicit `eventGroupId` values also connect different questions/thresholds in
one underlying event, and propagate overlap quarantine across them. Missing
event-family metadata must be reviewed before calling any future test split
independent. Public packets include an opaque `cohortGroup` to link them to the
private admission audit without exposing dispute or payout fields.

## Version 2 admission input (2026-09-14)

`app/scripts/research/disputes/prepare_gamma_from_map.py` turns the completed
dispute-to-catalog map into the Gamma-style input this pipeline expects: one
row per distinct catalog market version and `eventGroupId`, bound in
`sourceRefs` to the mapping manifest, the catalog version and every dispute
event that mapped to it, with only the classifier-read status fields lifted
from private state. It verifies every input hash and every event's raw line
hash and question ID before emitting a row, and writes `plan.json` and
`observations.json` (unmatched and unmapped requests, never admissions).
The v2 artifact lives beside v1 under a new write-once directory; its counts
are recorded in `docs/AGENT-HANDOFF-20260914.md`. Nothing is admitted to
training by it: every record stays `evidence_pending` with label review
required.

