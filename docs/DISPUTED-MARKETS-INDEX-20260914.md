# Disputed-market index — September 14, 2026

This is a separate research cohort for markets that have ever entered dispute,
including disputes still awaiting resolution. It must not be filtered to the
current `disputed` state or to already settled markets. A final `resolved` state
alone neither proves nor rules out an earlier dispute.

## Collected index and its limits

The final private index is
`~/.local/share/means-of-prediction/disputed-markets-20260914-union-v3/`.
Use v3 only; earlier unions are retained intermediate artifacts. Collection
exhausted the historical disputed-request query on three documented Polygon
oracle subgraphs, at separate pinned indexed blocks:

| Source | Indexed block | Dispute events |
|---|---:|---:|
| Original Optimistic Oracle | 93,803,127 | 23 |
| Optimistic Oracle V2 | 93,802,925 | 1,874 |
| Managed Optimistic Oracle V2 | 93,803,128 | 2,630 |
| Total | Separate snapshots | 4,527 |

There are 4,493 request occurrences with verified adapter-specific question-key
mapping, representing **3,879 distinct question IDs**. The other 34 requests
remain separate: 22 legacy-adapter requests need the old ancillary-hash lookup,
and 12 requests are outside the verified adapter mapping. Every occurrence is
retained; repeated dispute rounds are not counted as independent questions.

This is **not yet a complete list of platform-listed Polymarket markets**.
Question IDs identify adapter-associated questions; all Gamma market IDs and
condition IDs remain null. The source-specific query exhaustion is recorded as
`complete`, but it is not a claim that every historical deployment or platform
market is covered. The six configured adapter families are a coverage baseline;
the index still needs legacy joins and an independent platform-market join.

Actual dispute timestamps span **2021-10-19 22:41:07 UTC through
2026-09-14 17:48:28 UTC**. These use raw `disputeTimestamp`, not the request's
question timestamp. Captured states include later-settled and still-disputed
requests. A first challenge counts here even when Polymarket's resolution
subgraph reserves its `wasDisputed` flag for a later escalation.

The union provides `normalized-dispute-events.jsonl`,
`known-adapter-question-keys.jsonl`, and `unmapped-requests.jsonl`. Its plan and
manifest bind source inputs, output hashes and five official source-code
snapshots. Every record points to its raw response and SHA-256. Root checks
verified all 4,527 transaction/log/ancillary-data links, unique event keys,
question-key hashing, actual timestamps and private file permissions.

The original OOv2 normalization mistakenly used the indexed-head hash as the
individual dispute block hash. A preserved correction set that event hash to
null and kept the indexed-head hash separately; v3 uses the correction.
Earlier unions also used request timestamps for date summaries and assumed the
legacy adapter had the modern question-key formula. Those outputs are
superseded by v3. The OOv2 deployment/indexing-error metadata was checked only
in a later audit; the final manifest explicitly distinguishes it from metadata
captured at the other sources' frozen heads.

## Actual training-preparation result

The offline admission run is
`~/.local/share/means-of-prediction/disputed-training-cohort-20260914-v1/`.
It processed the 4,493 mapped request occurrences into 3,879 question groups.
All groups remain `mapping_pending`; there are **zero public judge packets and
zero reviewed training admissions**. The 34 unresolved mapping records remain
in the separate source index, outside this candidate training run.

The run binds four prior-ID input files, covering the old development and
reservation registries plus the new article sample. Missing market IDs prevent
a completed overlap join, so quarantine remains in place. Its curriculum
manifest applies to both regex and Qwen, is disabled, and proposes a 20% cap on
reviewed disputed cases once a later training experiment is prepared. No
training or settlement inference was launched. Nine focused tests passed,
including related-event grouping, conflict propagation and status parsing.

The next steps are the legacy ancillary-hash lookup, Gamma/condition/event
joins when public access is available, original-rule and evidence capture,
independent label review, and a separately frozen training/evaluation run. The
collector and admission commands are already completed and write-once; do not
rerun them into their existing directories.

## Source and coverage requirements

[Polymarket's resolution documentation](https://docs.polymarket.com/concepts/resolution)
describes dispute paths that can later resolve. Its
[resolution subgraph manifest](https://github.com/Polymarket/resolution-subgraph/blob/main/subgraph.yaml)
indexes multiple generations of standard and negative-risk adapters plus oracle
contracts. The configured adapter set includes legacy, v2, v3.1, v4, NegRisk and
NegRisk v4. It is a documented coverage baseline, not proof that all historical
contracts are included. `networks.json` and the YAML disagree on the v3.1 start
block; preserve and identify the selected configuration.

[UMA's official subgraphs](https://github.com/UMAprotocol/subgraphs) expose
historical dispute fields separately from settlement. Collect a pinned indexed
block with stable cursor pagination; retain deployment identity, indexing
errors, raw responses, request IDs and dispute transaction/log references.
Disputed requests that have subsequently settled remain eligible for indexing.
All UMA requests cannot be described as Polymarket markets: requester/adapter
lineage and question/condition/market joins require explicit provenance.
Unmapped requests remain a separate collection.

The existing local cache of 428,900 market rows retains only final resolution
markers and has no dispute history. A further bounded public-cache review found
189 Gamma records with `umaResolutionStatuses`, none explicitly containing a
dispute. Neither result establishes that these markets were never disputed.
A new direct Gamma API probe returned HTTP 403; no alternative tool was used
to bypass that denial.

## Counting and labeling

Report dispute event occurrences, unique oracle requests, question IDs, mapped
Polymarket markets and unmapped requests separately. Preserve repeated disputes
and later settlement transitions. Raw final payouts are observed oracle/API
outcomes, not automatically correct factual or evidence-answerability labels.
Capture time and market closure time are not original rule-version evidence.
Missing historical rules, missing evidence, invalid/void payouts and unresolved
cases must remain explicit.

## Training boundary

Use the separate disputed cohort to test source restrictions, timing, ambiguous
wording, conflicting reports and unsupported claims. Both regex and Qwen should
receive the same reviewed cases and grouped splits. Public reader inputs contain
only market terms and permitted evidence, excluding dispute status, proposed
prices, settlement outcomes and adjudicator discussion that reveals the answer.

Keep all related markets, repeat requests and dispute rounds together. Cases
linked to previously exposed or reserved market IDs are quarantined from fresh
splits. No raw dispute record is automatically admitted to training. Require a
reviewed evidence packet and separate labels for factual result, original-rule
answerability and observed settlement. Report this challenge cohort separately
from the ordinary-market benchmark; do not combine its score into a population
success estimate.

See [training integration](DISPUTED-MARKETS-TRAINING.md) for the importer,
quarantine policy and disabled-by-default curriculum manifest. Existing frozen
regex/Qwen experiments remain unchanged.

## Runtime

The collectors and question-key derivation use Ethereum Keccak-256 from
`pycryptodome==3.23.0`, pinned in
`app/scripts/research/disputes/requirements.txt`. The offline training-admission
module uses the Python standard library. Never substitute SHA3-256 for Ethereum
Keccak-256 when deriving question keys.
