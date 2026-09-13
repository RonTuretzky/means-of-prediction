# Real-data inventory and provenance repair

September 13, 2026. This records collection and integrity work, not a new
settlement accuracy result. The existing research inputs remain unchanged.

## Evidence inventory

The inspected development holdings contain 143 original NYT newsletters from
August 16 through September 12. All raw-email hashes match their recorded values.
The existing verification metadata records unrestricted-body DKIM passes for
143; this inventory did not rerun DNS or cryptographic verification. Contract
MIME support is a separate check. The selected natural factual benchmark uses
18 of these emails, 161 market/email pairs and 33 fact families.

No separately captured full NYT articles were found in the inspected holdings.
The HTML contains 10,518 tracking-link occurrences and 7,919 distinct hrefs;
these are not article counts. A separate 20-link article-access pilot completed:
all 20 resolved to distinct NYT article paths but returned HTTP 403 challenge
pages, so zero article texts were added. An ordinary browser fallback was rejected
before navigation by browser site-safety policy; no permission prompt or automatic
approval review was attempted. No alternate route was attempted after that
restriction. Full articles must not be treated as part of the signed email body.

The pilot froze links before requests, spanning 20 newsletter dates and five
coarse label-based topic groups. It recorded exactly 60 GETs (two redirects and
one publisher request per article), preserved all 143 source emails, and retained
missing title/canonical/publication metadata as null. Root verified all 116 sealed
file hashes, sizes and read-only permissions. Manifest hash:
`90589daa8e8e6478991bf086a14218fa789f6a5fdad5384c3d148c20f04ed277`.
This establishes the access result of the tested route and sample, not that the
articles do not exist or can never be accessed through an authorized route.

## Public market records

The exposed development universe contains 241 markets. Fifty-two already had
full public market responses from the expansion collections. A new bounded
collection captured the remaining 189 markets and 55 associated event responses
on September 13, from 22:25:20 through 22:26:23 UTC.

| Check on the 189-market repair | Result |
|---|---:|
| Successful market responses | 189/189 |
| Exact stored/current question, rules and ordered labels | 189/189 |
| Recorded winner agrees with new API result | 189/189 |
| Previously retained vectors agree | 184/184 |
| Older archive-only outcomes now have full API result records | 5/5 |
| Condition and question IDs in valid hex format | 189/189 |
| Failed requests or retries | 0 |

All new market records have closed/final markers and one-hot `outcomePrices`
vectors. These are current public API records, not independently verified
on-chain payouts. Agreement with stored rule text does not establish the rule
version at creation or exclude intermediate amendments. The five formerly
missing vectors remain null in the old-record fields; new records are separate.

The associated market/event responses contain 27 distinct source/context URLs.
No explicit clarification fields or clarification-candidate links were found in
those surfaces. Comments, histories and offsite destinations were not crawled;
absence of a discovered clarification is not proof none exists. The separate
`resolutionSource` field is nonempty for 71/189 markets; empty fields do not waive
source clauses in the rule text.

## Integrity and continuation

The collection audit recomputed all comparisons and winners, checked 244 raw
responses, and confirmed 93 prior source files were unchanged. Root separately
verified all 443 sealed file hashes, lengths and read-only permissions.

Private collection directory:

`~/.local/share/means-of-prediction/development-provenance-repair-20260913T222520Z/`

- Manifest SHA-256: `3f3d5a4550d9d260f3e45d471fcba8f49411f2ac13165f828282075d630d3b5a`
- Seal SHA-256: `c6d41588f099ca09f97f9a6836baeef1d0b3d8dd0a3f7e8f5a8230c41fbf3b7b`

The private manifest preserves exact request URLs, response bytes and hashes,
retrieval times, both old/new terms and vectors, identifiers and source pointers.
Constructed convenience market-page URLs were not validated; use captured API
URLs and retained event URLs for provenance. Collection involved no inference,
reserved evaluation evidence, or changes to frozen experiments.

The first real-email sufficiency review and bounded article pilot are complete;
see `REAL-ANSWERABILITY-V1-FINDINGS.md` for the separate annotation result.
The full 241-by-143 development cross-product is 34,463 candidate pairs, including
unrelated and unreviewed pairs. That count is neither confirmed coverage nor a
representative sample of the entire Polymarket platform. Any broader evaluation
must freeze its universe, observation window and treatment of multiple emails
before computing coverage.

## Follow-up on the three fixture-linkage cases

A separate read-only inspection selected only public identity and schedule
fields from four repaired market responses. It excluded prices, outcomes and
settlement fields and did not alter the sealed 60-pair labels or the running
source-check inputs.

The NFL market's captured `gameStartTime` is `2026-09-10 00:20:00+00`, which is
September 9 at 8:20 p.m. in New York. Its slug also explicitly names 2026.
Thus, the missing market year can be supplied from public metadata in a new
version of the input. The original four-field pilot did not include those fields.
The UMass winner, spread and total markets similarly supply
`2026-09-03 22:00:00+00`. Their metadata establishes the intended fixture year,
but does not itself add a game date to the newsletter's result report.

These observations distinguish recoverable input omissions from missing email
evidence. They are not new adjudicated labels or a revised accuracy result.
Any metadata-enriched evaluation must freeze these allowed fields, handle
timezones explicitly and adjudicate the revised inputs before joining outputs.
Current captured metadata also does not prove what every field contained at
market creation.

Private allowlisted inventory SHA-256:
`c606b2694b9d5ab4a12832632a24cb90ce2900bfc727256eae456dee2e71f49e`.
