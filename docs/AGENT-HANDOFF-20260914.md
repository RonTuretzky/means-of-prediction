# Means of Prediction — agent handoff

Verified September 14, 2026, at approximately 22:45 UTC. Read this first. It
supersedes older progress snapshots about the historical collection still
running, Gamma being generally unavailable, and every dispute lacking a market
mapping. Preserve those older records as history.

## Objective and current stopping point

The user wants to learn whether public prediction markets can settle reliably
from NYT evidence through two parallel methods: Astra-generated deterministic
regex rules, and Astra-generated plain-language rules judged by local
Qwen3.5-35B-A3B against the complete document. They want real data, expansion
beyond their newsletters to NYT articles, all available historical Polymarket
markets, and a separate disputed-market research cohort. They prefer inexpensive
local processing and bounded subagents of different models when useful.

The historical market expansion and its automatic finalizer are **complete**.
The finalizer finished at **2026-09-14T21:54:53.609258+00:00**. No matching
collection, finalizer, or research coordinator process was found at this
handoff's check. No new settlement inference or model weight training was run
for this expansion. The next work is usable article evidence, reviewed case
construction, and the remaining dispute joins—not restarting the import.

The original regex/Qwen experiments remain frozen. No new method has been
promoted to live settlement. A large market inventory is not itself a labeled
training set, and its size does not improve the measured accuracy.

## Workspace, Git, and user preferences

- Repository/worktree: `/Users/wk/conductor/workspaces/research/porto-novo`.
- Branch: `checkpoint/qwen-research-2026-09-13`.
- Correct remote: **`mop`**, `https://github.com/RonTuretzky/means-of-prediction.git`.
- **Do not push `origin`**: it points to the unrelated `RonTuretzky/research` repository.
- Verified code checkpoint before this documentation commit:
  `9fc6b2abbd4d5efa8797149e86740165d237f94d` (also verified on `mop`).
- Earlier checkpoints: `3f34bb92f929d535ffd27e2e7cf4ee64c2b2c9a8` for disputes;
  `02d4321efda4107d4b0dd99770233cc8fca522f1` for article preparation.
- Worktree was clean before writing this handoff. Preserve unrelated changes.
- Commit as the configured user, with **no assistant co-author trailer**.
  The user previously authorized commits and pushes to this project.
- Private data base: `/Users/wk/.local/share/means-of-prediction`.
- Private configuration: `/Users/wk/.config/means-of-prediction`.
- Keep credentials, full mail, full articles, raw model responses, private labels,
  and large raw captures out of Git, public issues, and published slides.
- The Git repository does not contain the private corpus. A different machine
  needs a private transfer of relevant data/configuration; cloning alone is insufficient.
- Open requested slideshows in the computer's **Google Chrome** by default.
- Research slideshow: `https://ronturetzky.github.io/means-of-prediction/research-results/`.
  It presents the earlier email findings; the large catalog has not been added.
- Broader user instructions are in `/Users/wk/AGENTS.md`; shape-rotator tool
  instructions are at `/Users/wk/shape-rotator-field-kit/AGENTS.md` if using that kit.

## Completed historical market catalog

| Measure | Verified result |
|---|---:|
| Open/default pages | 1,709 |
| Open/default saved raw row occurrences, including a repeated page | 170,803 |
| Original open manifest counter | 170,703 |
| Closed pages | 31,414 |
| Closed saved raw row occurrences | 3,141,318 |
| Union input files, including older local captures | 37,605 |
| Union source rows / recorded versions | 3,868,525 |
| Unique market IDs | 3,308,079 |
| Markets with consistent question/rules/ordered labels | 3,308,078 |
| Markets quarantined for conflicting public terms | 1 |
| Held-out/exposed market IDs flagged in catalog | 1,253 |
| Rejected rows without IDs | 0 |

The open counter discrepancy is explained: pages 137 and 138 repeated the same
100 market IDs/cursor request during a legacy resume. Both raw responses remain
preserved. The independent cursor/hash audit records `duplicateRequests: 1`
and `manifestOccurrenceCorrection: 100`; the final catalog deduplicates IDs.
Previous brief status replies quoted the legacy 170,703 counter as raw rows.
Use the audited 170,803 raw-occurrence count when describing saved inputs.

Both API partitions exhausted their opaque cursors. This covers the records
returned by the public API during the scan, not deleted/private records or an
atomic snapshot. Markets can change partitions while a scan runs. Earliest
closed-market creation was `2020-10-02T16:10:01.467Z`. The open capture's legacy
name includes “all,” but the documented endpoint defaults to `closed=false`;
its `scope-correction.json` binds this correction. The closed capture explicitly
used `closed=true`. No date or sample cutoff was applied to these API scans.

Keyset documentation:
`https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination`.
Use documented limits, opaque cursors, normal rate limits and Retry-After. The
working keyset endpoint is separate from an earlier failed dispute-filter probe.

### Exact artifact paths

| Path | Contents |
|---|---|
| `/Users/wk/.local/share/means-of-prediction/historical-market-catalog-20260914/manifest.json` | Final counts, input bindings, per-partition cursor/hash audits, output hashes |
| `/Users/wk/.local/share/means-of-prediction/historical-market-catalog-20260914/catalog.sqlite3` | Private master database, 9,536,835,584 bytes |
| `/Users/wk/.local/share/means-of-prediction/historical-market-catalog-20260914/candidate-public.jsonl` | Terms-only candidates, 3,771,529,918 bytes; includes explicitly flagged holdouts |
| `/Users/wk/.local/share/means-of-prediction/historical-market-all-api-20260914` | Completed open/default raw gzip pages, request log, frozen legacy collector, correction |
| `/Users/wk/.local/share/means-of-prediction/historical-market-closed-api-20260914` | Completed explicit closed raw pages, strict collector snapshot, plan, log and manifest |
| `/Users/wk/.local/share/means-of-prediction/historical-catalog-expansion-run-20260914/state.json` | Final phase `complete`, catalog and dispute-mapping counts |
| `/Users/wk/.local/share/means-of-prediction/historical-catalog-expansion-run-20260914` | Frozen `source/`, launch plan, historical PID record, build and mapping logs |
| `/Users/wk/.local/share/means-of-prediction/polymarket-pages` | Earlier 4,289-page / 428,900-row capture |
| `/Users/wk/.local/share/means-of-prediction/nyt` | Older mailbox research data and partial/review market inputs |
| `/Users/wk/.local/share/means-of-prediction/development-provenance-repair-20260913T222520Z/responses/markets` | 189 earlier full Gamma responses used in the union |

Database SHA-256:
`e9195018291fbe17b6f79660ac5fbd06ccf76813f6d03743cd7db50c0f35288d`.
Candidate JSONL SHA-256:
`54489490c5499b85521fb9be0c574b35526bfc04dc56bc157f8d0de3579582b6`.
Use the manifest for other hashes. Do not load these multi-gigabyte files into
an agent's context; query SQLite read-only or stream selected fields.

The database has `sources`, `versions`, `markets`, and `rejections`. Versions
retain source path/hash/row, raw row hash, question/condition/event IDs, public
terms and private state observations. Multiple public term values cause a
conflict; a changed status alone does not. `candidate-public.jsonl` contains
`marketId`, `question`, `rules`, ordered `outcomeLabels`, and `trainingHoldout`.
It is not a ready-to-train file: filter holdouts, build connected event/story
groups, and review evidence before admission. Private state contains outcomes
and status and must not be copied into blind generator/judge inputs.

Catalog source: `/Users/wk/conductor/workspaces/research/porto-novo/app/scripts/research/catalog`.
There are 11 catalog/audit/mapping/finalizer tests plus 4 collector tests, last
run successfully before the collection finished. Frozen code performed the
completed data audits/build. Do not rerun the write-once build into its existing
output or resume completed captures. The removed legacy collector remains in
its private capture; use `collect_partition.py` for any genuinely new capture.

## Separate dispute index and mapping

The authoritative source union is
`/Users/wk/.local/share/means-of-prediction/disputed-markets-20260914-union-v3`.
Use **v3 only**. Earlier unions have superseded timestamp/legacy-key assumptions.

- 4,527 unique dispute events across original OO (23), OOv2 (1,874), and managed
  OOv2 (2,630), at respective pinned blocks 93,803,127 / 93,802,925 / 93,803,128.
- 4,493 event/request occurrences have verified adapter question-key mappings,
  representing 3,879 distinct question IDs.
- The remaining 34 records are in `unmapped-requests.jsonl`: 22 legacy-adapter
  requests need `AncillaryDataHashToQuestionId` lookup; 12 are other requesters.
- Actual dispute times span 2021-10-19T22:41:07Z–2026-09-14T17:48:28Z.
  First challenges, later-settled disputes and unresolved disputes are retained.

The completed Gamma join is
`/Users/wk/.local/share/means-of-prediction/dispute-catalog-map-20260914`:

| Measure | Count |
|---|---:|
| Input mapped-question occurrences | 4,493 |
| Occurrences matched to catalog versions | 2,892 |
| Unmatched occurrences | 1,601 |
| Matching catalog versions | 2,908 |
| Distinct matched question IDs / market IDs | 2,385 / 2,385 |
| Distinct question IDs still unmatched | 1,494 |

Read its `manifest.json`, `mapped-private.jsonl`, and `unmatched-private.jsonl`.
Mapped records retain every source version, condition/event IDs, holdout flags
and private state; they are not public judge packets. The 1,601 unmatched
occurrences are distinct from the 34 requests without verified question keys.

The earlier admission artifact at
`/Users/wk/.local/share/means-of-prediction/disputed-training-cohort-20260914-v1`
still says all 3,879 groups are `mapping_pending`. That old artifact was not
rewritten. A future version must integrate the new mapping, propagate prior-ID
quarantines across connected events, and review evidence/labels. Current reviewed
training admissions remain zero. Proposed 20% disputed-case curriculum share is
a starting configuration, not a measured optimum, and is disabled.

Source modules:
`/Users/wk/conductor/workspaces/research/porto-novo/app/scripts/research/disputes`
and `/Users/wk/conductor/workspaces/research/porto-novo/app/scripts/research/catalog/map_disputes.py`. The separate root audit
is `/Users/wk/.local/share/means-of-prediction/disputed-index-root-audit-20260914/audit.json`.
Use Ethereum Keccak-256 (`pycryptodome==3.23.0`) for key derivations, not SHA3-256.

## NYT articles: exact access blocker and available preparation

The user has an NYT subscription and reports being logged in. Their account
has **not been tested through the blocked browser route**. The archived event is:

`/Users/wk/.local/share/means-of-prediction/article-access-pilot-20260913T223148Z/browser-access-policy-event.v1.json`.

It records `cua.createBrowserTab` blocked before navigation, with the reason:
“The site-safety policy blocks browser use on the requested www.nytimes.com
article.” No login inspection, automatic approval review, or user permission
prompt occurred. Separately, 20 unauthenticated HTTP link chains received
terminal NYT 403 challenge responses; they did not use the signed-in browser.
Do not diagnose a missing subscription or licence as the demonstrated technical
failure. Do not bypass the block through other browsers, cookies, proxies,
mirrors or indirect routes. Do not ask for the user's password again.

Actual full article bodies collected: **zero**. NYT public API-style and RSS
records provide metadata, not complete article text. Newsletter bodies already
held privately remain a distinct evidence corpus.

| Private path | Available preparation |
|---|---|
| `/Users/wk/.local/share/means-of-prediction/nyt-article-registry-20260913` | 8 RSS feeds; 215 occurrences, 178 distinct URL identities, 0 full bodies |
| `/Users/wk/.local/share/means-of-prediction/article-market-universe-20260913-v3` | Valid frozen sample of 1,000 markets / distinct event groups; earlier versions superseded |
| `/Users/wk/.local/share/means-of-prediction/nyt-rss-market-retrieval-20260914` | 21 lexical candidate pairs for 16 markets; 984 sample markets unmatched |

Those matches are discovery leads, not answerable cases or an accuracy/coverage
estimate. RSS dates span September 7–14; 66 of 178 identities are later than the
earlier market window. Retrospective retrieval does not prove that the captured
article version existed at resolution time.

Importer code: `/Users/wk/conductor/workspaces/research/porto-novo/app/scripts/research/articles`.
Collection/freezer/matcher code: `/Users/wk/conductor/workspaces/research/porto-novo/app/scripts/research/article_collection`.
Schema and usage: `/Users/wk/conductor/workspaces/research/porto-novo/docs/ARTICLE-CORPUS-PIPELINE.md`.
The implemented full-text CLI accepts **normalized JSONL exports** with text,
identity, provenance, publication/retrieval dates and completeness. Earlier short
replies loosely said HTML/PDF support; raw HTML or PDF must first be converted
with original-file provenance retained. There is no direct HTML/PDF importer
command. Declared complete text is stored as an unverified submitter declaration.

## Existing method quality and frozen experiments

Read `/Users/wk/conductor/workspaces/research/porto-novo/docs/REAL-ANSWERABILITY-FULL-V1-FINDINGS.md`.
Of 161 selected real market/email pairs, 1 is answerable under original source
rules, 157 have insufficient contained evidence, and 3 remain unresolved.
The only answerable pair is market 3709179, the reporting-permitted Tupac
conviction case. Qwen recovered it; regex missed it. This is one event, not a
credible 100% versus 0% projected success rate.

| Frozen baseline view | Correct / 1 answerable | Claims on 157 insufficient pairs | Failures / 161 |
|---|---:|---:|---:|
| Regex candidate detector | 0 | 60 | 3 |
| Qwen direction | 1 | 110 | 18 |
| Same Qwen outputs, exact-quote filter | 1 | 80 | 18 |

Older factual-recovery scores were regex 63/161 (39.1%), Qwen 75/161 (46.6%), and
quote-filtered Qwen 55/161 (34.2%). They measure a different question and must
not be described as valid settlements under the original market rules. The
source-check pilot is also separate; it reduced unsupported quoted claims from
32 to 26 on 53 common insufficient cases but did not establish a promoted method.
Model-based dual reviews/adjudication are not independent human ground truth.

| Private path | Purpose |
|---|---|
| `/Users/wk/.local/share/means-of-prediction/slides/astra-qwen-nyt-round1-20260912` | Main Qwen rules, prompts, immutable calls, feedback and runtime |
| `/Users/wk/.local/share/means-of-prediction/slides/astra-nyt-round4-20260912` | Completed regex experiment and preserved independent test |
| `/Users/wk/.local/share/means-of-prediction/slides/parallel-track-review-20260913/ROOT-REVIEW-STATUS.md` | Detailed private experiment decisions and recovery history |
| `/Users/wk/.local/share/means-of-prediction/slides/real-answerability-v1-20260913` | Original 60-pair review |
| `/Users/wk/.local/share/means-of-prediction/slides/real-answerability-remaining-v1-20260913` | Complementary 101-pair review, combined label seal and baseline comparison |
| `/Users/wk/.local/share/means-of-prediction/slides/real-answerability-combined-independent-review-20260913` | Independent full-inventory audit |

V2 and the old probes are complete. Original V3 was interrupted; only its 194
provably unattempted local calls were completed in a separate continuation.
Combined V3 accounting: 1,910 valid judgments, one original capped failure,
four original uncertain requests never retried. Keep original completion markers
absent; do not rewrite history or restart those requests. V3 is not promoted.
V4–V6 helpers exist but no new full-round launch or weight fine-tuning follows
automatically from finishing this catalog.

Detailed continuation constraints and histories:

- `/Users/wk/conductor/workspaces/research/porto-novo/docs/QWEN-RESUME-HANDOFF.md`
- `/Users/wk/conductor/workspaces/research/porto-novo/docs/QWEN-V3-INTERRUPTION-CONTINUATION.md`
- `/Users/wk/conductor/workspaces/research/porto-novo/docs/QWEN-SOURCE-CHECK-V1.md`
- `/Users/wk/conductor/workspaces/research/porto-novo/docs/RESEARCH-NEXT-STEPS-20260913.md`

Read current banners before historical commands. Internal exact-input review
records attest to an agent's completed checks; they are not automatically a
requirement to ask the user for permission again.

### Models and protected evaluation data

Coordinator model may change. The live generator/teacher for new work is
Claude Fable 5.1 (`claude-fable-5-1`), selected by
`app/scripts/research/blind/fable_transport.py`; see
`docs/FABLE-GENERATOR-TRANSPORT.md`. Every completed round was generated by
`gpt-6-astra` through `astra_transport.py`, which stays unchanged as the
request-shape witness for those frozen artifacts. No Fable draw has been run
yet; this machine had no Anthropic credential at the swap.
Blind rule generation sees only frozen public market inputs, never this
conversation, target evidence, payouts, or labels. A historical market can also
be familiar from pretraining; public-only prompting is not proof of absence of
model prior knowledge. Teacher feedback may use declared development evidence.

Pinned local judge: LM Studio instance `mop-qwen35b-research`,
`http://127.0.0.1:1234`, model `qwen3.5-35b-a3b`, Q4_K_M, 21,169,116,992-byte GGUF,
SHA-256 `f25d609171b8f80950a60f38696597f74025de4070682d2fb1eeffe306ca7d5d`.
Archived runtime: context 131,072; 4 workers; temperature 0; seed 20260912;
2,048 output tokens; LM Studio 0.4.1+1; backend
`llama.cpp-mac-arm64-apple-metal-advsimd@2.13.0`; SDK 1.4.0. Consult the private
main Qwen root's `runtime.json` for exact paths. Recheck service/model identity
before any new inference; it was not queried or launched for this handoff.
Do not unload unrelated models or run competing local judge coordinators.
Archived research scripts use Python 3.14.6 and `tiktoken==0.14.0`; older Python
versions can fail runtime seals. Preserve quota failures; do not consume usage
resets or switch models/accounts without authorization.

Protected reservations:

- `/Users/wk/.local/share/means-of-prediction/qwen-evaluation-reservation-20260912`
  contains the sealed independent 12-question/120-fixture evaluation. Its
  `provenance/excluded-market-ids.json` is the allowed 253-ID exclusion registry.
- `/Users/wk/.local/share/means-of-prediction/supplemental-natural-evaluation-20260913-125243`
  contains sealed two-email/241-question provisional annotations (482 pairs).
- `/Users/wk/.local/share/means-of-prediction/slides/paired-natural-evaluation-20260913`
  is the prepared supplemental evaluation procedure.
- `/Users/wk/.local/share/means-of-prediction/article-market-universe-20260913-v3/sampled-public-inputs.json`
  binds the 1,000 additional IDs held out by the catalog.

Do not inspect sealed fixture bodies/labels to plan training, search old
dataset-authoring conversations for them, or leak the regex independent test
into Qwen. IDs and manifests can be checked without opening protected contents.
Final method selection, public rule draws, input/runtime freezes, and exact
evaluation gates must precede opening reserved evidence.

## Next work, in order

1. Read this handoff and the small final manifests. Query the completed catalog
   read-only. Report inventory, available full evidence, answerable cases, and
   outcome agreement with distinct denominators.
2. Use the new dispute join to prepare a separately versioned admission input,
   retaining all unmatched requests and propagating prior-ID/event-family
   quarantines. Investigate the 1,494 unmatched question IDs and 34 unmapped-key
   requests using verified adapter/platform provenance. Do not manufacture joins
   from outcome agreement or drop hard cases to improve coverage.
3. Obtain usable article text through an allowed export/content route. The
   browser blocker remains unresolved; a signed-in account alone did not remove
   it. Convert acquired exports to the documented JSONL schema, preserving
   source bytes, URL, authorship when available, publication/update/retrieval
   timestamps, date precision and version hashes.
4. Build a scalable metadata retrieval index over the catalog and available
   article registry. Use source/entity/event/date constraints to select leads;
   do not make an LLM call for each of 3.3 million markets or assume every market
   has NYT coverage. Retain unmatched cases as coverage observations.
5. Freeze the next population, time window and grouped splits before reviewing
   target evidence. Keep related markets, thresholds, event IDs, repeated
   stories/articles and dispute rounds together. Later-captured rules or
   corrected articles do not prove historical version availability.
6. Independently review full text against original source, timing and factual
   conditions. Separate factual result, original-rule answerability and observed
   payout. One NYT report does not establish required official evidence or
   reporting consensus. Preserve insufficient, unresolved and invalid reviews.
7. Test one bounded change per path: regex story/headline-to-summary binding with
   original spans and rejection of cross-story joins; Qwen evidence extraction
   plus deterministic comparison for supported numeric families. Freeze exact
   procedures and gates, compare contemporary baselines, retain failures/repeats,
   and keep synthetic unit/control examples outside the primary real-data score.

Separately authored markets explicitly using NYT reporting can form a future
prospective benchmark. Do not rewrite existing Polymarket rules to create more
positives. There is currently too little real answerable evidence for a
population accuracy estimate. For more design detail read
`/Users/wk/conductor/workspaces/research/porto-novo/docs/HISTORICAL-MARKET-RESEARCH-PLAN.md`.

## App, contracts, worker, and sensitive configuration

These are broader project context, not newly verified live deployment status.
Research continuation should not deploy/promote a settlement method by implication.

- Frontend: `/Users/wk/conductor/workspaces/research/porto-novo/app/src`.
- Foundry contracts/tests: `/Users/wk/conductor/workspaces/research/porto-novo/contracts`.
- Deployment records: `/Users/wk/conductor/workspaces/research/porto-novo/contracts/deployments`,
  with `gnosis.json`, `sepolia.json`, and `local.json`.
- Email connector: `/Users/wk/conductor/workspaces/research/porto-novo/app/scripts/mailbox.mjs`;
  daily coverage script: `/Users/wk/conductor/workspaces/research/porto-novo/app/scripts/research/daily.mjs`.
  Current recurring-job state was not
  inspected for this handoff; use the product automation tools when asked.
- Mailbox configuration: `/Users/wk/.config/means-of-prediction/mailbox.json`.
  It already contains private access configuration. Do not print its values.
- Cloud worker configuration/provider/SSH material:
  `/Users/wk/.config/means-of-prediction/worker`.
  Service configuration is under its `service/collector` and `service/signer`.
  Do not repeat credentials pasted in earlier messages or place them in prompts.
- Worker operator code: `/Users/wk/conductor/workspaces/research/porto-novo/ops/settler`.
  Read `/Users/wk/conductor/workspaces/research/porto-novo/docs/AUTO-SETTLEMENT.md`
  before operating it. That doc's last live verification is September 10.
- Recorded cloud worker: DigitalOcean `mop-email-settler`, droplet 599386463,
  host `159.203.92.112`; Sepolia chain 11155111. Factory
  `0xdbe9c7f2333a0705eefcac15c58d70859b5b1e2f`; body store
  `0xb15d8bf694aab06731d7debb17adac22b10ac3b1`.
- Recorded server layout: `/opt/mop/current`, `/opt/mop/releases`,
  `/etc/mop/collector`, `/etc/mop/signer`, `/var/lib/mop-settler`,
  `/var/lib/mop-signer`. Private backup copies:
  `/Users/wk/.local/share/means-of-prediction/worker-backups`.

The app's implemented path uses RSA-SHA256/DKIM authenticity and bounded body
parsing, with a registrar trust boundary for domain keys. Documented limits are
192 KiB body, 4 KiB witness and 24,000-byte upload pages. Pagination distributes
submission; it does not remove final verification cost or body limits. Research
article text is not automatically DKIM-authenticated email evidence. The cloud
worker submits accepted YES proofs; it does not use the research Qwen judge or
automatically derive NO from absent mail. Its synthetic Sepolia end-to-end tests
are recorded, not evidence of real Polymarket settlements.

New deployments have a default 1% protocol fee per buy/sell, alongside the
creator LP fee; old clones cannot gain fees retroactively. See
`/Users/wk/conductor/workspaces/research/porto-novo/docs/FEES.md`,
`/Users/wk/conductor/workspaces/research/porto-novo/docs/BODY-PARSING.md`,
`/Users/wk/conductor/workspaces/research/porto-novo/docs/DKIM-PROVENANCE.md`, and
`/Users/wk/conductor/workspaces/research/porto-novo/docs/GASKILLER-LLM-SETTLEMENT.md`.
Backlog: `https://github.com/RonTuretzky/means-of-prediction/issues/1` (size/cost)
and `https://github.com/RonTuretzky/means-of-prediction/issues/2` (GasKiller).
Original research links supplied by the user:
`https://www.paradigm.xyz/writing/pm-amm`,
`https://github.com/NubsCarson/hyperbet-market`, and
`https://github.com/PlayHyperia/hyperbet`. Do not treat those links as adopted designs.

## Safe starting commands

These are read-only or synthetic-test commands, not production actions. Large
file hash checks are optional if transferring data; manifests already contain
the completed pipeline's output hashes.

```sh
cd /Users/wk/conductor/workspaces/research/porto-novo
git status --short
git branch --show-current
git log -3 --oneline
jq '{phase,updatedAt,catalogCounts,disputeMappingCounts}' /Users/wk/.local/share/means-of-prediction/historical-catalog-expansion-run-20260914/state.json
jq '{counts,artifacts,exclusionInputs}' /Users/wk/.local/share/means-of-prediction/historical-market-catalog-20260914/manifest.json
sqlite3 -readonly /Users/wk/.local/share/means-of-prediction/historical-market-catalog-20260914/catalog.sqlite3 '.schema markets'
python3 -m unittest discover -s app/scripts/research/catalog/tests -p 'test_*.py'
python3 -m unittest app.scripts.research.catalog.test_collect_partition
python3 -m app.scripts.research.articles --help
```

Before starting any worker, inspect actual processes and existing completion
artifacts. Historical PID files are provenance, not proof that a process is
alive. Tool calls that return a session ID indicate an ongoing process; poll
that session rather than starting another writer. Keep new runs in new private
directories, retain raw failure receipts, and use the existing code's locks and
replay checks.

Suggested opening prompt for the next agent:

> Read `/Users/wk/conductor/workspaces/research/porto-novo/docs/AGENT-HANDOFF-20260914.md`
> first. The 3,308,079-market catalog and separate dispute mapping are complete.
> Continue the real-data research plan from those artifacts, preserving all
> frozen experiments and holdouts. The immediate bottleneck is usable NYT full
> article evidence; the browser tool blocked navigation before testing login.
> Work on permitted data preparation and remaining dispute joins, using cheap
> local processing and bounded subagents where useful. Keep Fable 5.1 as generator
> and the pinned local Qwen as judge; do not rerun completed collectors, open
> reserved labels, infer new accuracy from catalog size, or deploy research
> methods. Use the `mop` Git remote and keep private data and credentials local.
