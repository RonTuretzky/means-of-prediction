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

## Adversarial review of "one alert per newspaper, headline only, K outlets" (October 3)

Proposal from the project owner: an alert stream per newspaper, the judge reads only the
headline (at most 100 characters), and redundancy across K outlets makes that enough.
Five independent red-team passes attacked it (attacker economics, semantics, Google as
single signer, protocol, alternatives); the planned second-reviewer pass could not run
(account session limit), so the attack list is one-sided. The central claim was checked
here against our own data instead: Jev read every headline of the 120-market calibration
probe, headline only, and markets were settled at K distinct outlets.

| setting (Jev, headline only) | K=1 false YES / true YES | K=2 | K=3 |
|---|---|---|---|
| all 896 outlets, p ≥ 0.5 | 17/56 · 29/55 | 12/56 · 27/55 | 9/56 · 24/55 |
| registry outlets, p ≥ 0.5 | 5/56 · 23/55 | 4/56 · 17/55 | 3/56 · 12/55 |
| registry outlets, p ≥ 0.7 | 1/56 · 12/55 | 1/56 · 9/55 | 1/56 · 6/55 |

(false YES = NO-resolved markets with K outlets' headlines read as YES; true YES =
YES-resolved markets reaching K; 56 NO and 55 YES judged markets.)

Verdicts that hold on this evidence:

1. **Redundancy does not buy what was claimed.** Raising K removes true settlements
   about as fast as false ones, because every outlet writes the same headline about the
   same event and the judge misreads all of them together. At the settings that keep
   false YES near zero, only one in five true-YES markets settles at all.
2. **The residual false YES is a true headline about the wrong market**, at zero
   attacker cost: sibling and date-bucket markets ("SpaceX IPO on June 26" when the IPO
   was June 11; "The Voice of Hind Rajab wins Best International Feature" against "Oscars:
   winners list in full"). A 100-character headline has no room for the qualifier, there
   is no per-result timestamp, and K repeats the same omission. In the probe 6 to 8 of 63
   NO markets are exactly this shape.
3. **Recall collapses on headline alone.** For 22 of 57 YES markets no headline on any
   outlet states the outcome (thresholds, counties, sub-categories, line-ups, "full
   winners list" headlines without the name). Settlement is YES-or-void, so most
   true-NO markets and most true-YES markets end in a refund.
4. **K hosts are not K sources.** Wire copy, one upstream call, and premature calls
   repeated within minutes; 10 of 68 multi-outlet markets in the probe carry an exact or
   near-identical headline pair across registry outlets.
5. **Per-newspaper streams make best-of-N worse.** A site:-only alert is the outlet's
   whole output; daily and weekly digests show exactly 10 results whatever the window,
   so most stories are dropped and the submitter's search space is every headline the
   outlet published. The reported 1,000-alert cap also rules out per-newspaper-per-market
   alerts.
6. **The headline is Google's rendering**, not the outlet's: Google rewrites a majority
   of title tags and has run unlabelled AI-generated headlines in Search since March
   2026; 19% of real alert headlines in the samples end in an ellipsis.
7. **Protocol gaps the headline does not touch**: the prover chooses which emails to
   submit; a challenger cannot obtain a signed alert after the fact unless they
   subscribed beforehand; void at par pays the losing side for withholding; raw emails
   carry the collector's address and a per-alert token that lets anyone edit or kill the
   alert.

What survives, and the design that follows:

- **One topical alert per market, not per newspaper.** Query frozen at market creation
  and bound to the signed Subject; outlet identity enforced by the contract's host
  allowlist with path rules; as-it-happens delivery.
- **The judge reads headline + snippet + the signed send time + the Fable rule**
  (event instance, sibling list, not-counted phrasing). The snippet is admitted as the
  weaker field and tested separately for forced false YES.
- **Market admission rule for this evidence class:** only outcomes a headline can carry
  (named subject plus a conventional completed-event verb); no "on date X" buckets, no
  thresholds, ordinals or scope qualifiers; sibling families settle only by exclusivity,
  and a headline naming a sibling's winner counts as NO evidence. The contract, not the
  judge, enforces the date window from the rule's event instance.
- **K over independent originations**: ownership and wire families collapsed, near-
  identical headlines deduplicated, at least one non-wire original, the K emails spread
  over hours, a 24-72 hour challenge delay; ellipsis-truncated headlines rejected.
- **Independent collectors** (two or three) subscribed to every frozen query, logging a
  hash of each received email on arrival; only logged emails are admissible. This is what
  makes the challenge delay real.
- **Google stays one evidence class among two.** Newsletter signers remain for markets
  that should not rest on a single signer and index; a weekly canary compares alert
  headlines with the outlets' own feed titles.

Open until measured on real alerts: per-account divergence, as-it-happens email shape,
delay and hit rate for market outcomes, and how far the GDELT stand-in is from what
alerts deliver.

## First real alerts (October 6): format census and the GDELT gap

477 alert emails reached the owner's Gmail between October 2 and 6, every one of them
filed in **Spam** by Gmail (none in the inbox; Spam is purged after 30 days). All 477
were pulled over IMAP and stored privately (`alerts_mail.py`, root
`~/.local/share/means-of-prediction/alerts-mail-20261006/`), the google.com key record
was snapshotted, and a 40-message sample verifies under selector `20251104`.

| measured on 477 emails, 3,226 results | value |
|---|---|
| MIME, signer | multipart/alternative; d=google.com, s=20251104, no `l=`, `x=` = t + 7 days |
| signed headers | content-type, to, from, subject, message-id, list-unsubscribe, list-id, date, mime-version (from, to, cc, subject, date, message-id, reply-to, content-type oversigned): Content-Type **is** signed on current mail, unlike the 2025–May 2026 public samples |
| raw size | median 30 KB, max 223 KB |
| results per as-it-happens email | median 4, max 46; 83 emails with one result, 76 with ten or more: no ten-result cap |
| headline length | median 78, max 110 characters; 113 end with an ellipsis; 1,747 end with " - Publisher" |
| snippet length | median 147, max 162; 2,190 of 3,226 end with an ellipsis |
| sections | News only |
| hosts | 834 distinct; reuters.com 348, bbc.com 241, **youtube.com 212**, apnews.com 196, theguardian.com 166, nytimes.com 147; **polymarket.com 30** (market pages surface as News results for these queries) |
| volume by alert type | the five `site:` census alerts: 213 emails, 983 results; the 18 event-level alerts: 263 emails, 2,242 results, most of them from the five broad topics (Anthropic IPO, Fed decision, Israel–Iran, US–Iran, shutdown); the narrow ones fired two to four times in three days |

**The GDELT stand-in misses most of what alerts deliver.** Matching the 3,226 results
against the GDELT Article List for October 2–5 (`alerts_fidelity.py`): 697 found, 22%
(23% excluding YouTube). Zero of 348 Reuters, 196 AP, 17 Washington Post, 21 Bloomberg,
17 CNN results are in GDELT and 4 of 147 NYT; the Guardian (71%), Al Jazeera (71%), CNBC
(95%), Jerusalem Post (94%) and CBS (88%) are well covered. Where both exist the headline
is byte-equal after removing the outlet suffix in 444 of 697 cases and a truncation of
the other in 112; the snippet is not the GDELT description (median token overlap 0.11).
Alerts arrive a median 10.7 hours after GDELT's first sighting (quartiles 2.7 to 18.2),
and before it in 78 cases.

Consequences: the Jev-labelled GDELT corpus is trained on a different outlet mix from
the one alerts deliver and cannot stand in for the wire services or the New York Times;
the real alert stream, about 1,000 results a day from these 23 alerts, is the right
training and evaluation source from here on, and the units must be the alert's own
headline and snippet. YouTube and market pages in the News section make the host
allowlist non-optional. Gmail's spam filing means collection must not depend on an
inbox: pull every folder, or set a filter that keeps alert mail out of Spam.

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
