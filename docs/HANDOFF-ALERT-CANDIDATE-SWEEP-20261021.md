# Google Alerts candidate sweep — 21 October 2026

## Outcome

The most interesting independently ranked demo is **“Nobel Peace Prize 2026 awarded to an individual?” (market 5371292)**. Collected signed excerpts name Navi Pillay. The fixed student supports the committee-domain excerpt and a much smaller BBC excerpt. This is a retrospective demo candidate, not an executed settlement or demonstrated pre-resolution advantage.

The whole permitted local raw corpus was inventoried and parsed; every in-scope result received deterministic screening. **454 exact result excerpts received explicit individual decisions: the original 443 plus 11 new Nobel evidence records. The remaining 30,677 in-scope excerpts do not have explicit individual decisions.** Do not call this an exhaustive manual review or an accuracy benchmark.

## Scope and coverage

All new artifacts are private under:

`/Users/wk/.local/share/means-of-prediction/alerts-candidate-sweep-20261021/`

| Measure | Count |
|---|---:|
| Distinct raw Google Alerts messages / distinct Message-IDs | 4,561 / 4,561 |
| Parsed result occurrences | 32,096 |
| Exact distinct URL/headline/publisher/snippet units | 31,729 |
| Canonical article URLs, with conservative tracking removal | 28,087 |
| Article URLs with distinct useful excerpts retained | 2,764 |
| In-scope units screened | 31,131 |
| NYT-linked units / personal or rent units excluded | 585 / 13 |
| Units routed by saved queries / broad-query units without direct routing | 29,567 / 1,564 |
| Potential query-routed market/unit pairs / markets | 379,675 / 1,206 |
| Exact written individual decisions after Nobel follow-up | 454 |
| Frozen inference excerpts / distinct markets | 21 / 15 |

The four raw stores are `alerts-proof-monitor/raw` (3,912 files), `alerts-mail-20261006/raw` (675), `mail-routing-cleanup-20261020/raw` (120 Google Alerts among 202 files), and general `raw` (2 Google Alerts among 19,408 files). Non-Alert messages in mixed stores were classified from headers only. One malformed header was rechecked with the compatibility parser and classified as non-Alert without reading its body.

All 7,835 occurrences in the old forward export and all 192 monitor bundle-export rows match inventoried raw evidence. The forward export has 7,770 distinct market/full-result pairs; the older headline/URL unit key counted 7,635 and collapsed some distinct excerpts. Both Google Alerts records in `mail.sqlite` match raw hashes. No extra raw evidence was hidden in that database. Current parsing loses zero saved results; one added result was an excluded rent item.

The full inventory includes eight verified expansion maps: 332 queries and 1,624 markets, all with original rules. The original forward map brings the union to 347 query strings and 1,656 markets. Existing explicit A/B predicates cover only 28 expansion markets; 1,596 lack them. Exact public metadata versions are absent for 153 of the union's markets. New shortlist predicates are manual demo translations, **not a new blind Astra-generation evaluation**.

## Authentication and exclusions

All 4,561 canonical bodies match their declared DKIM body hashes. Separately, complete RSA/header/body verification was replayed offline for **4,502 in-scope messages**, using preserved public-key snapshots: all passed with the verifier clock at signed time. At the actual wall clock, 3,500 passed and 1,002 were expired. No body-length-limited signature or missing required/singleton header was accepted.

This proves arithmetic against the cached key. It does not establish historical DNS ownership, DNSSEC provenance, independent receipt time, publisher authorship or truth. No fresh DNS/mail collection occurred. The remaining 59 messages were excluded by query scope; raw-message and result-level exclusions overlap and must not be added together.

Sealed reservations remained unopened: 5,823 market IDs were conservatively quarantined, alongside metadata describing 4,000 calibration units, 108,272 heldout units and legacy evaluation reservations. None of the 15 selected markets overlaps the excluded market-ID union. Unit-level training overlap is not proven absent. Historical GDELT/Google News alert-shaped corpora were inventoried as metadata; they are not genuine signed email and were not re-opened as candidate evidence.

The latest saved mailbox collection reports a `TimeoutError`. This sweep covers persisted local data, not all mail currently on the server. `/tmp/galerts_research` is absent. NYT/newsletter work remains excluded.

## Independent selection and actual inference

Selection, labels, ranking, original rules, source limits and tokens were frozen before any new inference. All 21 inputs retain their state under the existing 320-token / 160-head-token limits. The exact final calibrated profile from the previous milestone was reused:

```text
Weights SHA256: 5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169
Profile SHA256: 8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835
Selection SHA256: e1d0372ed3556f9eaa3a346764596b9580f4c6d92dd3c7e08b60093fd1a08a6d
Freeze SHA256: 1191792e1f5e0161ec82a350083b57b9b47a628b85e52292b466c8d30b1d9944
Results SHA256: 652cd1d06c46332def26b5fbb0fd6787195d86e52d077a204dc720d893d8861b
```

Temperature remains `1.1089085340499878`; A and B are independent rounded probabilities at `0.55`. Diagnostic q is not a fallback decision. Every case ran all 28 encoder layers and two decision-head layers in CPU float32. Every stock replay matched exactly. No retraining, calibration change or post-score prompt adjustment occurred.

| Selected evidence | pA | pB | Frozen reference vs result |
|---|---:|---:|---|
| Nobel committee-domain excerpt | .8465 | .0556 | A / A |
| Nobel BBC excerpt, 20,461-byte body | .8931 | .0529 | A / A |
| Holborn by-election, smaller local report | .8629 | .4003 | A / A |
| Official F1 GP pole excerpt | .3936 | .2673 | A / abstain |
| Spain call, Reuters excerpt | .5379 | .0683 | A / abstain |
| China GDP 4.5%, TradingView/SeekingAlpha | .6342 | .0827 | A / A; initial NBS release unproven |
| China GDP, official snippet with number omitted | .1051 | .2801 | neither / neither |
| Yokohama election | .4168 | .7549 | A / B |
| New Westminster election | .4009 | .5607 | A / B |
| Preserved Brewers baseline | .5846 | .0318 | A / A, exact prior result |

Overall: **9/21 exact reference matches, ten abstentions on expected support, two opposite B flags**. All four strict neither-support controls were retained. Full results, including the other variants, are in `shortlist-results.private.json`. These are purposively selected diagnostics, not projected deployment accuracy.

The two opposite B flags expose an additional predicate problem: “A different candidate won that election” does not name the target, while each B question is independently serialized. Do not attribute the disagreement solely to the model. Likewise, an F1 pole headline and the stricter “fastest official qualifying time” predicate are not automatically interchangeable. Frozen labels and scores remain unchanged; the diagnostic q output was not substituted to force a pass.

## Recommended demo and remaining gates

Use the **Nobel individual-laureate** story as the next retrospective demo. Frozen rank 2 is a BBC result with the decisive sentence naming Navi Pillay and the 2026 Peace Prize. It fits the current body/window limits and yields A only. Rank 1 is the committee-domain excerpt, but its complete canonical body is 239,824 bytes, above the fixed 196,608-byte limit. Do not crop the authenticated body or silently change the parser profile. An AP corroborating excerpt exists in a separate 44,883-byte body in `sports-awards-shortlist.private.json`; it was independently reviewed but not one of the 21 scored inputs.

Public market route, verified against the saved mapping's exact `eventURL`: `https://polymarket.com/event/nobel-peace-prize-2026-awarded-to-an-individual`.

Mandatory unresolved gates remain: admit the exact named source/first announcement or credible consensus; distinguish Google-relayed excerpts from publisher-signed evidence; establish historical key and receipt/closure policy; bind authenticated extraction and tokenization; execute the complete deterministic integer model and GasKiller certificate; apply consumer conflict/deadline rules and settlement/redemption. No new on-chain proof or settlement occurred.

### Nobel chronology and source policy

The focused timing audit rechecked seven raw hashes and their authentication receipts without repeating inference. Signed timestamps are:

| Saved evidence | DKIM signed time (UTC) | Interpretation |
|---|---|---|
| Earliest Peace/Pillay wave, including AFP and The Hindu | October 9, 11:51:35 | Earlier reporting than the frozen committee/BBC examples |
| Earliest direct AP winner article | October 10, 02:47:15 | A separate named newswire origin; its “2026 Elections” fragment is navigation, not prize-year evidence |
| Earliest direct Reuters winner article | October 10, 07:55:23 | Headline explicitly identifies the 2026 Peace Prize |
| Frozen committee-domain excerpt | October 11, 02:50:16 | Full body exceeds parser v2 cap |
| Frozen BBC excerpt | October 18, 02:58:28 | Small complete body passes parser v2 |

The candidate IDs containing `20261009` are descriptive and do not encode the actual message time. Use the original signed timestamps above. The timing audit preserves stored `Received` headers separately; those headers and saved review timestamps are not an independently attested first collection time.

For Peace market 5371292 and Chemistry market 5371179, the saved snapshots omit actual `closedTime`. Searching 428 saved discovery captures found no target-market record and does not establish closure. A far-future configured `endDate` is not proof the market remained open. Chemistry's October 7, 11:51:48 email precedes its declared end by 58,032 seconds, but preclosure is still unproven. Keep all examples retrospective.

The committee winner excerpt links `nobelpeaceprize.org`, whereas the exact rule names the first announcement at `nobelprize.org`. The collected `nobelprize.org` announcement snippet names the committee/date but does not name a laureate. The rule permits credible-reporting consensus as a fallback, but outlet diversity alone does not establish independence: AFP reprints, agency feeds and repeated Reuters versions count once per origin. Do not add missing event-year or first-announcement facts from the owner-controlled query, Subject, navigation text or an unrelated article's “related stories” section. The separate source review retains 13 detailed evidence records and four timed bundles. It reports 275 source inspections, including 4 overlapping the initial 443, but compact displays could truncate excerpts. We therefore count only its 13 detailed records (2 overlapping) toward explicit per-unit decision coverage: 454 total. The mixed-depth union is 714 inspected units, not 714 fully adjudicated cases. No additional model scoring was performed.

Newly located city outcomes include Vancouver/Pete Fry, New Westminster/Daniel Fontaine and Surrey/Doug McCallum. Some arrived through alerts for another city, illustrating why cross-market matching matters. Source consensus and event/date gates remain separate from the reader's text judgment. China GDP supplies the number and a separate official snippet, but the official snippet omits the number: concatenation does not establish that the reported value was the required **initial** NBS release.

## Files and reproducibility

The private directory contains:

- `raw-inventory.private.json`, `source-audit.private.json`, `derived-source-coverage.private.json`, `derived-parser-comparison.private.json`, `text-dedup.private.json` — source accounting and deduplication.
- `messages.private.jsonl`, `units.private.jsonl`, `screening.private.jsonl`, `query-screening.private.json`, `screening-summary.private.json` — indexed evidence and corpus-wide screening.
- `market-inventory.private.json` — exact rules, query joins, source captures, timing and exclusion metadata.
- `existing-candidate-review.private.json`, `existing-reviewer-full-index-followup.private.json`, `sports-awards-shortlist.private.json`, `macro-candidate-review.private.json`, `broad-query-review.private.json`, `semantic-review-coverage.private.json` — independent reviews and coverage limits.
- `authentication.private.jsonl`, `authentication-summary.private.json` — cached-key complete DKIM replay.
- `shortlist.private.json`, `shortlist-frozen.private.json`, `shortlist-frozen.sha256`, `shortlist-results.private.json` — write-once selection and inference.
- `sweep-audit.private.json`, `checkpoint.private.json` — original compact audit and updated continuation.
- `nobel-source-review.private.json`, `nobel-timing-review.private.json`, `nobel-oversize-design.private.md`, `nobel-supplement-audit.private.json` — Nobel source groups, exact timing limits, safe size design and final supplemental audit.
- `nobel-fixtures.private.json`, `nobel-fixtures.sha256`, `nobel-parser-tests.log` — private complete original bodies and observed five-test parser result.

All scripts below reside in the private directory and ran with `/Users/wk/.local/share/means-of-prediction/venv-laya-py312/bin/python`:

| Command | Observed completion |
|---|---|
| `sweep_inventory.py` | exits 0, sessions 54157 and 55645; second run corrects legacy relative raw paths |
| `triage.py` | exit 0, session 82908 |
| `authenticate_offline.py` | exit 0, session 78167 |
| `assemble_shortlist.py` | exit 0 |
| `score_shortlist.py freeze` | exit 0, session 56435, PID 5471 |
| `score_shortlist.py run` | exit 0, session 26331, PID 6127 |

Freeze and inference are write-once; do not rerun them in this completed output directory. Preserve this failure record. For a later diagnostic, independently preregister self-contained predicates in a new directory before scoring; do not tune against these results and present the retest as blind accuracy.

## Nobel full-body parser checks and size strategy

The separate private `export_nobel_fixtures.py` now exports the original BBC and committee complete canonical bodies, signed-header witnesses and exact four-field HTML windows. It validates the source bytes against the frozen selection and the independent cached-key DKIM replay. The prior Brewers exporter and fixtures remain unchanged.

Fixture SHA256: `521e6317c29b3a2610fd0c83e6cf6ea3929524ae63a4663e1944287cd29886ae`.

| Witness | Complete body | Original encoded window | v2 result |
|---|---:|---:|---|
| BBC, signed October 18 | 20,461 bytes | offset 8,078, length 1,265 | accepted |
| Committee, signed October 11 | 239,824 bytes | offset 38,663, length 1,340 | rejected above 196,608-byte cap |

`contracts/test/NobelAlertRealBody.t.sol` ran with the private fixture explicitly supplied: **5 passed, 0 failed, 0 skipped** (session 63513, exit 0). It verifies the genuine BBC full body, rejects a mutation outside the selected window, rejects a changed excerpt/wrong offset, rejects the oversized committee message, and rejects cropping that body to the current limit. Measured BBC full-body parser call gas: **17,576,952** in the local Foundry configuration. This is pure MIME/full-body `bh=` binding; it does not execute Solidity RSA, tokenizer, model, a certificate or settlement.

Reproduce from `contracts/`:

```sh
LAYA_NOBEL_MIME_FIXTURE=/Users/wk/.local/share/means-of-prediction/alerts-candidate-sweep-20261021/nobel-fixtures.private.json forge test --match-contract NobelAlertRealBodyTest -vv
```

The private `nobel-oversize-design.private.md` specifies a separate parser v3 with a 245,760-byte cap and a matching new request domain/policy, preserving v2 and every model/calibration pin. This is **a design, not an implemented or measured v3 verifier**. The fixture's additional `withinProposedBound262144` field is only an exploratory size comparison and does not define an admitted parser policy. The alternative is an authenticated incremental SHA-256/MIME state machine over ordered bounded chunks; chunk storage or a Merkle root alone cannot prove the DKIM body hash. Both approaches must process every original byte. The design includes boundaries, adversarial tests, RSA composition requirements and gas limitations.

Next engineering step: compose full-header RSA with the candidate-bound MIME check and the trusted request policy, then implement authenticated extraction/tokenization and the deterministic runtime/certificate/consumer. If the committee source is required, build and measure the explicitly versioned larger parser before deciding whether authenticated streaming is necessary. A larger size constant alone is not deployability or a settlement proof.

No mailbox cleanup, automation edits, collection, deployment, wallet/funding action or GitHub comment occurred. A brief mistaken return to the historical inbox task performed only a connector profile lookup and read saved cleanup receipts; no messages or settings were changed, and the trusted Nobel delegation was rechecked before continuing. The canceled issue #4 comment remains canceled. Existing source changes and the previous 56-test milestone are preserved. The only added contract source in this sweep is the five-test Nobel fixture suite; production parser/request sources were not changed. No commit or push was performed.


## October 21 expanded notability sweep — latest research result

Priority was corrected to a broader ranked shortlist before any further single-candidate engineering. No new inference, training, calibration changes, transactions, deployment, subscriptions, outreach, or mailbox mutations were performed in this sweep. The paused gate/exporter files remain untested drafts.

The concise shortlist has **five mapped market families**, rather than ten padded with weak or unmapped stories. Ranking follows the user's Nobel preference, event significance, complete rule semantics and evidence quality; it is not selected by model success.

| Rank | Exact market / event | Independent evidence finding | Existing model only | Principal remaining limit |
|---|---|---|---|---|
| 1 | 5371292 — Nobel Peace Prize 2026 awarded to an individual? | Yes: BBC explicitly names Navi Pillay as 2026 laureate; Reuters and AP corroborate. Human rights and international justice make this the preferred showcase. | BBC A 0.8931; committee A 0.8465. | Actual closure/first receipt absent. Committee first-announcement capture is 239,824 bytes and wrong literal primary domain; use the rule's credible-reporting route with explicit provenance. |
| 2 | 5371179 — Will Takuzo Aida win the Nobel Prize in Chemistry in 2026? | No under admitted complete winner set: Reuters explicitly says prize goes to a pair, names Kagan/Soai and 2026; AP corroborates. The count-and-identity bridge is affirmative evidence, not mere nonmention. | Prior exact early Reuters excerpt abstained: A 0.0297, B 0.2728. | Current DKIM expiry and actual closure remain unresolved for prospective execution. Original October 7 Reuters version and October 8 AP version both fit and precede the saved declared end; do not backdate later article versions. |
| 3 | 5371237 — Will Susan Athey win the Nobel Prize in Economics in 2026? | No if Hall/Woodford are admitted as the complete pair. AP/Reuters name winners; DW explicitly supplies the complete-pair wording. Economically significant work on stabilization. | No existing score for this market. | DW body 199,832 exceeds 196,608 by 3,224 bytes. AP's '2 American economists' is nationality-qualified, so the fit-sized AP/Reuters subset alone lacks a strict cardinality witness. |
| 4 | 5206978 — Spain snap election called by October 31? | Yes under permitted credible-reporting consensus: BBC confirms November 29 polls and Reuters reports the completed October 5 call. Literal rule permits formal scheduling OR dissolution, not a mandatory decree specifically. | Previously scored BBC and Reuters excerpts abstained; Reuters A 0.5379. Newly selected BBC result 24 was not scored. | October 5 signatures expired October 12. Saved creation October 2 and open October 6 snapshot support chronology; actual closure/first receipt unavailable. |
| 5 | 2953634 — Will China GDP growth in Q3 2026 be between 4.3% and 4.6%? | Reported 4.5% supports the numerical Yes predicate. Caixin and Seeking Alpha via TradingView are named source groups. | TradingView A 0.6342; Caixin abstained A 0.4565. | Required initial NBS release/value is missing; alert is October 19, before scheduled October 20 release. Factual lead, not rule-complete settlement evidence. |

All source links, full rules, exact excerpts, raw hashes, result indices, signed times, Received-header claims, body sizes and authentication receipts are in the private final shortlist. Dates are signature claims, not independently attested first receipt. Full RSA/body/header replay against cached Google keys proves relay bytes, not publisher authorship, reporting independence, historical DNS ownership, or truth. Current versus signed-time validity is explicit per occurrence. No onchain settlement occurred.

### Body and timing inventory for the selected evidence

- Peace: BBC October 18, 20,461 bytes; Reuters October 10, 142,915; AP October 10, 44,883. BBC current-time replay passed at audit; the earlier wires expired.
- Chemistry: original Reuters October 7 11:51:48Z, 166,050 bytes; AP October 8 02:48:03Z, 95,589. Later Reuters October 8 07:49:56Z, 111,580 is preserved as an alternative, never substituted into earlier chronology. Official/NHK corroboration 218,353 is oversized. Current signatures expired.
- Economics: DW October 12 11:15:33Z, 199,832 (oversized); AP October 13 02:47:49Z, 77,703; Reuters October 14 07:49:50Z, 172,385. AP/DW expired; selected Reuters was current-valid at audit time.
- Spain: BBC October 5 14:31:00Z, 112,100; Reuters October 5 14:53:18Z, 62,474. These small raw messages were already in the prior frozen sweep. Progress here is deeper rule review and an additional BBC excerpt, not a newly received result or newly solved size problem.
- China GDP: two reporting excerpts in the same October 19 08:55:04Z email, 73,617. One authenticated email is not two independent signed publishers. Current-time replay passed; mandatory source/version still absent.

### Coverage and exclusions

The merged inventory contains **4,861 unique emails**, 33,216 exact excerpts and 29,465 canonical article URLs. Of these, **32,596 excerpts were mechanically screened**; 607 NYT-host excerpts and 13 rent/personal-query excerpts were excluded. Conservative sealed-market exclusion remains 5,823 market IDs. No forbidden dataset rows or outcome prices were read for selection.

Detailed documented decision coverage rose from **454 to 550**: 104 detailed units in this sweep, eight already in the baseline, thus **96 additional**. The union of verified full excerpt inspections is **924**; 374 of those do not have equivalent detailed source-specific adjudications. **32,046 in-scope excerpts still lack detailed decisions.** This is not exhaustive semantic review. Truncated/compact displays and lexical screening are not silently promoted into this count. Full-email bodies were cryptographically checked; this does not mean every result in every email received semantic review or is eligible for monitor archival.

Cached-key full-signature/body/header replay passed at signed time for all **4,802 in-scope messages**; 3,799 passed at the audit clock, 1,003 had expired. Fifty-nine out-of-scope messages were excluded from authentication. The current collection remains bounded and incomplete: 300 additional saved messages, no reported collection failures, resume from **17-Oct-2026**.

Notable Physics (Halzen) and Literature (Carson) stories have strong relayed reporting but no eligible exact-market/full-rule mapping, so they are not invented as market candidates. Equifax omits EPS; Roadster has live/recorded conflict; AfD speakership is not state government; Taiwan drills are not a 24-hour blockade; FDA and climate snippets miss their exact official predicates. Sports and games do not dominate the shortlist.

The prior frozen model diagnostic remains **9/21 matches**, with its original failures and abstentions preserved. This selected sample is not a projected deployment accuracy. No new model scoring was run; attaching old single-excerpt scores does not score the new evidence bundles.

### Continuation paths

Private root: `/Users/wk/.local/share/means-of-prediction/alerts-notability-sweep-20261021/`.

- `ranked-shortlist-final-frozen.private.json`: authoritative five-event independent ranking, exact complete rules, evidence and boundaries. Earlier frozen revisions are retained with explicit supersession chains.
- `existing-model-results.private.json`: unchanged prior model cases attached after final independent review freeze; exact-excerpt identity is explicit.
- `coverage-audit.private.json`: deduplicated detailed and full-inspection unit IDs and denominator arithmetic.
- `science-awards-review.private.json`, `science-awards-review-audit.private.json`, `politics-world-review.private.json`, `politics-world-coverage-correction.private.json`, `macro-product-review.private.json`, `health-climate-review.private.json`: reviewer evidence and coverage corrections.
- `messages.private.jsonl`, `units.private.jsonl`, `screening.private.jsonl`, `authentication.private.jsonl`: merged inventory, lexical screening and offline complete-signature replay. `market-inventory.private.json` is a symlink to the immutable prior inventory; do not edit its target.
- `audit.private.json`, `checkpoint.private.json`: final validation and continuation status.

Engineering stays paused: `/Users/wk/.local/share/means-of-prediction/nobel-gate-20261021/engineering-checkpoint.private.json` and `/Users/wk/.local/share/means-of-prediction/nobel-input-20261021/checkpoint.private.json`. Gate/exporter drafts are UNTESTED; no compile, parity, new gas result, or settlement claim. Preserve the pre-existing modified `app/scripts/research/blind/alerts_email.py` and all other dirty files.

Next research can target the remaining specific gates: missing exact markets for Physics/Literature, preclosure/first-receipt records, complete Economics pair evidence in a smaller genuine email, and the actual initial NBS release. Freeze any new independent judgments before new scoring. Keep case-specific source admission separate from model truth scores and from executable proof. Do not resume implementation merely because the shortlist is delivered without respecting the latest owner direction.
