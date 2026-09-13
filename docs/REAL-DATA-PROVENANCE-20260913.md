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
these are not article counts. A 20-link article-access pilot is being collected
separately. Full articles must not be treated as part of the signed email body.

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

Next, finish the real-email sufficiency review and the bounded article pilot.
The full 241-by-143 development cross-product is 34,463 candidate pairs, including
unrelated and unreviewed pairs. That count is neither confirmed coverage nor a
representative sample of the entire Polymarket platform. Any broader evaluation
must freeze its universe, observation window and treatment of multiple emails
before computing coverage.
