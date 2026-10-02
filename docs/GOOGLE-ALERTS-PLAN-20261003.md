# Google Alerts as the evidence source: findings and plan (October 3, 2026)

Decision under test: settle markets from Google Alerts emails instead of (or alongside)
newspaper newsletters. One signer, google.com, then covers every outlet Google indexes;
the evidence unit shrinks from a newsletter of tens of kilobytes to one alert result of
about 250 characters; and markets no longer depend on which stories an editor put in a
newsletter. Roles: **Fable** writes each market's factual predicates from the public
terms, blind to the outcome; **Jev** reads alert results and says whether they report a
predicate as a completed fact; the **open student** is distilled from Jev so that the
deployed judge is re-executable; real payouts are a consistency check, never a label.

## What an alert email is (verified on real 2025–2026 emails)

Seven raw alert emails published in public repositories and two already in the private
research mailbox were parsed and their DKIM signatures recomputed.

- **Signer.** `From: Google Alerts <googlealerts-noreply@google.com>`, `d=google.com`,
  rsa-sha256, relaxed/relaxed, RSA-2048, no `l=` tag (the whole body is signed). Signed
  headers include To, From, Subject, Date, Message-ID; the top-level Content-Type is not
  signed. Every signature carries `x=` equal to signing time plus seven days.
- **Key rotation.** Selector `20230601` signed alerts in October 2025 and is now revoked
  in DNS; `20251104` signs them from at least May 2026. Old emails verify only against an
  archived key, so keys must be pinned by hash and DNS snapshotted at collection time.
- **Body.** multipart/alternative: a text/plain part, then a quoted-printable HTML part.
  A ten-result email is 55–62 KB. In the HTML each result is one schema.org `Article`
  row.
- **Per result, exactly four fields**: the headline (page title, at most 100 characters,
  median 82, sometimes ending " - Outlet"), a publisher label assigned by Google, a
  snippet (at most 160 characters, median 147, an extract that usually ends in an
  ellipsis and can contain navigation text or other stories' headlines), and a link
  `https://www.google.com/url?rct=j&sa=t&url=<article URL>&ct=ga&…`. There is no
  per-result time, author or body. The email-level time is the signed Date / `t=`.
- **Subject** is `Google Alert - <query>`: the alert owner's own text.

`app/scripts/research/blind/alerts_email.py` parses a raw email into these units from
the HTML part; `unit_text()` is exactly what a judge reads (headline, publisher label,
snippet).

## What the signature proves, and the rules that follow

It proves that Google's alert mailer sent these bytes to this recipient at this time.
It does not prove any outlet published anything: headline, label and snippet are
Google's rendering of third-party page text, and fake pages built to trigger alerts are
a documented abuse. Consequences, none optional:

1. Outlet identity comes only from the host of the article URL inside the result's own
   link, checked against a per-market allowlist, with path rules that exclude press
   releases, sponsored and contributor content. Never from the label or a headline
   suffix.
2. Pin `From` exactly, the key by hash (both known selectors, with validity windows),
   and the body structure (one `Article` row in the HTML part). Not "any google.com
   mail".
3. **Never accept Subject evidence from this signer.** The deployed verifier would
   accept a Subject-only proof once the google.com key is registered, and the Subject is
   the prover's own query. The google.com key must not enter any registry used by
   Subject or Subject-or-body markets.
4. Evidence window from the signed Date / `t=`; the seven-day `x=` expiry is a stated
   policy choice (ignored, or proofs due within seven days).
5. K distinct allowlisted outlets, challenge delay, void at par by default: unchanged
   from research plan v2. Alerts widen coverage; a small set of independent newsletter
   signers stays for markets that should not rest on one signer.
6. Raw alert emails are never published: they contain the recipient address and a live
   per-alert token. Dedicated collection accounts only.

Verification cost: the current on-chain verifier rejects these emails (body profile v1
accepts single-part text only). Cheapest step is an "alerts" body profile taking a
quoted-printable window inside the HTML part. A private proof is feasible natively
(Noir/UltraHonk about 80 gates per body byte; a 48 KB body about 4M gates, half a
minute, 7 GB; about 2M gas to verify). As-it-happens alerts with one result should be
much smaller; that needs a real sample.

## Training data: only what an alert could carry

The unit is one alert result: headline, publisher label, snippet, outlet host. Nothing
else from the page is admissible, so nothing else is used for training.

- **Backfill source: GDELT Article List (GAL).** Per article: title, a one-sentence
  description (median 146 characters), domain, outlet name, URL, and the file time as a
  "seen by" stamp. Free, redistributable with citation, no API key. Gaps: almost no
  Reuters, AP, Washington Post, WSJ, Politico, FT, Axios, USA Today records; those need
  the NYT/Guardian APIs and Wayback-captured outlet feeds, or are accepted as gaps.
  `gal_download.py` keeps English records per day.
- **Google News RSS is not used for the corpus**: no snippet, day-level times, and its
  terms and robots.txt rule out bulk use. A 120-market calibration sample exists
  (`alerts_probe.py`); coverage there: 111 of 120 markets had headlines in the ten days
  before close, 85 from at least one outlet already in the on-chain key registry, 68
  from two or more.
- **Proxy fidelity is unknown** until real alerts are compared with GAL for the same
  queries. Real snippets are noisier than GAL descriptions. Only forward collection
  closes that.
- **Markets.** Every event group in the resolved credible-reporting pool, up to three
  markets per group (the winner plus losing siblings): 19,783 markets, 10,390 groups,
  7,425 resolved YES and 12,358 NO.
- **Rules.** `rules_batch.py`: Fable, 25 markets per call, blind, returns factualA,
  factualB, eventInstance, notCounted per market.
- **Labels.** Jev on every (alert-shaped unit, market) pair, uncapped locally; the
  OpenRouter key's own daily dollar limit is the only brake.
- **Checks.** A YES claim on a NO-resolved market is a definite false claim; reported
  per market over its whole window, with K outlets, never per unit.

## Forward collection (needs the user)

Alerts cannot be backfilled and have no API. A dedicated Google account, alerts created
by hand: Sources News, How often As-it-happens, How many All results, English/US,
Digest off, delivered by email; raw messages pulled through the existing IMAP intake;
the google.com DKIM record snapshotted with each message. First goal is a format census
(as-it-happens size and result count, digest shape, the 1,000-alert limit), then alerts
for the forward-test markets with the query frozen in the pre-registration.

## Running now, and where

| job | command / script | output |
|---|---|---|
| Fable rules, 19,783 markets | `rules_batch.py` | `slides/alerts-rules-20261003/rules.jsonl`, log `slides/alerts-rules-20261003.log` |
| GAL download, 2025-05-20 to 2026-09-16, newest first | `gal_download.py` | `~/.local/share/means-of-prediction/gdelt-gal/en/YYYY-MM-DD.jsonl.gz`, log `gdelt-gal.log` |
| Calibration probe, 120 markets | `alerts_probe.py` | `slides/alerts-probe-20261002/` |
| Market sample | `alerts_probe.py sample --per-group 3` | `slides/alerts-corpus-20261003/sample.private.json` |

(`slides/` is `~/.local/share/means-of-prediction/slides/`.)

## Next, in order

1. Pair: for each market, GAL records inside its window that match its entities, in
   alert shape, capped per market.
2. Jev labels every pair with the Fable rule; payout-consistency and coverage tables.
3. Distil a headline-and-snippet student from those labels; compare headline-only
   against headline plus snippet (the snippet is the weaker, more attackable field).
4. Forward census on the dedicated account; measure how far GAL is from real alerts.
5. Contract: an alerts market type (signer pin, outlet host allowlist, body profile v2),
   only after the census.
