# Handoff: Google Alerts evidence track (state as of 2026-10-03, 16:00 JST)

Goal: settle prediction markets from Google Alerts emails (DKIM-signed by google.com)
read by a small open judge distilled from Jev, with Fable writing each market's factual
predicates blind to the outcome. This document lists what exists, what is running, where
everything is, and what to do next. Read `docs/GOOGLE-ALERTS-PLAN-20261003.md` first:
verified anatomy of an alert email, the trust rules, and the adversarial review with the
revised design. The newsletter-student work it builds on is in
`docs/HANDOFF-LAYA-DISTILLATION-20260927.md`.

## Alerts created on the owner's Google account (October 3)

Created by hand through google.com/alerts under the owner's sign-in; 21 email alerts, all
set to How often **As-it-happens**, Sources **News**, Language English, Region Any, How
many **All results**, Deliver to the owner's Gmail. Google rejects a second alert with an
identical query, so the two RSS probes use quoted variants and kept Google's defaults
for Sources and How many (Automatic, Only the best results).

Event-level alerts, one per open market family (markets close October 25 to November 30):

```
Anthropic IPO
Israel next prime minister
midterm elections House control
midterm elections Senate control
California billionaire wealth tax
Russia Ukraine ceasefire agreement
NATO Russia military clash
Israel Iran ceasefire
US Iran nuclear deal
"Kanye West" Russia
"GTA 6" release date
"Strait of Hormuz" fees
"Cy Young" award winner
midterm elections governor results
Serbia prime minister
Nobel Prize winner announced
Federal Reserve interest rate decision
government shutdown ends
```

Outlet census alerts (delivery volume, truncation, results per email for a whole-outlet
stream; expect hundreds of emails a day in total):

```
site:reuters.com   site:apnews.com   site:bbc.com   site:nytimes.com   site:theguardian.com
```

RSS probes (per-entry timestamps, unsigned, for delay measurement): `"Anthropic IPO"`,
`"Nobel Prize"`. Feed URLs are recorded at the end of this file.

What to do with the mail: keep every raw message with full headers (the existing IMAP
intake, or Gmail API `format=raw`); never publish one (recipient address and a live
per-alert edit/unsubscribe token are inside the signed body); snapshot the google.com
DKIM TXT record for the selector seen in each message (currently `20251104`) because the
previous key was revoked within a year. Parse with
`app/scripts/research/blind/alerts_email.py`; `unit_text()` is exactly what a judge may
read for one result (headline, publisher label, snippet).

## How past-market training data is made from current real alerts

Alerts cannot be backfilled, so resolved markets are paired with a stand-in: the GDELT
Article List (title, one-sentence description, outlet, domain, URL, minute file time),
which carries the same four fields an alert result shows. The real alerts above are the
yardstick for that stand-in:

1. **Shape**: real results are headline up to 100 characters, snippet up to 160, usually
   ending in an ellipsis, often with " - Outlet" appended to the headline. Apply the
   same truncation and suffix rules to GDELT titles and descriptions before judging or
   training, so the student never sees cleaner text than an alert will give it.
2. **Fidelity**: for each alert query, run the same query against the local GDELT index
   over the same days (`gal_index.py`) and compare: share of alert URLs present in GDELT
   within one day, share of hosts in common, headline equality or edit distance, snippet
   versus description similarity, and delay between GDELT file time and alert send time.
   This yields a filter (which GDELT records an alert would have carried) and a transform
   (how Google rewrites text). Two weeks of alerts over the 18 event-level queries is
   enough for a first estimate.
3. **Outlet mix**: the census alerts show which hosts Google's News section actually
   delivers for major outlets; the allowlist used for K-outlet settlement should be built
   from observed alert hosts, not from the newsletter key registry alone (only 4% of
   GDELT units sit on registry hosts).

## Pipeline and artifacts (private, under `~/.local/share/means-of-prediction/`)

| stage | script (repo `app/scripts/research/blind/`) | output |
|---|---|---|
| market sample: every event group in the resolved credible-reporting pool, up to 3 markets per group | `alerts_probe.py sample --per-group 3` | `slides/alerts-corpus-20261003/sample.private.json` (19,783 markets, 7,425 YES / 12,358 NO) |
| Fable rules per market (factualA, factualB, eventInstance, notCounted), 25 markets per call, blind | `rules_batch.py` | `slides/alerts-rules-20261003/rules.jsonl` (13,640 of 19,783 at hand-off; job running, resumable) |
| GDELT Article List, English, 2025-05-20 to 2026-09-16 | `gal_download.py` | `gdelt-gal/en/YYYY-MM-DD.jsonl.gz` (485 days, 10 GB) |
| full-text index and per-market pairing (rarity-ranked entities, 10 days before close to 2 after, cap 60) | `gal_index.py build` / `pair` | `gdelt-gal/gal.sqlite3` (55.9M rows); `slides/alerts-corpus-20261003/pairs.private.jsonl` (17,465 of 19,783 markets with units, 714,789 units) |
| Jev labels on (unit, market) pairs with the Fable rule: pA, pB, pQuestion | `alerts_label.py`, chain `slides/alerts-label.sh` | `slides/alerts-corpus-20261003/labels-alerts.private.jsonl` (running; ~380,000 pairs for markets with rules; the OpenRouter key's $1/day limit is the only cap, the chain waits and resumes) |
| calibration probe (Google News RSS, 120 markets, headline only; not licence-clean for bulk) | `alerts_probe.py` | `slides/alerts-probe-20261002/` (`judged-jev`, `judged-laya`, `summary.json`) |
| real alert email parser | `alerts_email.py` | (real samples from public repositories are in `/tmp/galerts_research/*.eml`, temporary, other people's mail; keep out of the repo) |

Logs sit next to each root: `slides/alerts-rules-20261003.log`, `gdelt-gal.log`,
`gdelt-gal.index.log`, `slides/alerts-corpus-20261003.pair.log`,
`slides/alerts-corpus-20261003.label.log`, `slides/alerts-label.log`.

Relaunch commands (all resumable):

```sh
V=~/.local/share/means-of-prediction/venv-laya-py312/bin/python
cd ~/conductor/workspaces/means-of-prediction/newport-beach/app/scripts/research/blind
RR=~/.local/share/means-of-prediction/slides/alerts-rules-20261003
MOP_CLAUDE_CODE_BIN="$CLAUDE_CODE_EXECPATH" nohup $V rules_batch.py --root $RR --sample $RR/sample.private.json --batch 25 --workers 4 >> $RR.log 2>&1 &
nohup ~/.local/share/means-of-prediction/slides/alerts-label.sh > ~/.local/share/means-of-prediction/slides/alerts-label.log 2>&1 &
```
`MOP_CLAUDE_CODE_BIN` must point at a Claude Code binary that supports Fable (2.1.251 or
newer); when it fell back to the stale `~/.local/bin/claude` (2.1.236) every batch failed
with `model_mismatch`. The teacher key lives only in
`~/.config/means-of-prediction/openrouter.json`.

## Results so far

- Coverage of the GDELT stand-in: 17,465 of 19,783 markets have at least one candidate
  unit in their window; median 49 units per market; 10,148 distinct hosts.
- Calibration probe, Jev reading headlines only, registry outlets, p ≥ 0.7: false YES on
  NO-resolved markets 1 of 56 at K = 1, 2 or 3; true YES 12, 9, 6 of 55. Raising K buys
  nothing; the residual false YES is a true headline about a sibling market. Full table
  and the adversarial review in the plan document.
- Jev labels on the alert-shaped corpus: in progress; first pass costs about $0.00005 per
  pair.

## Next steps, in order

1. Let the rules and labels finish (about a day at the key's limit; raise the limit on
   OpenRouter to finish in hours).
2. Payout-consistency and coverage tables per market at K = 1, 2, 3 with the Fable rules,
   on registry hosts and on all hosts; the admission rule from the review (no date
   buckets, thresholds or ordinals; siblings by exclusivity) applied as a filter.
3. Distil the alert-shaped student from the labels with the v3c recipe
   (`laya_distill.py`: side-contrast weighting, positive augmentation), input =
   headline + publisher + snippet; evaluate headline-only against headline + snippet.
4. First real alert emails: run `alerts_email.py` on the raw messages, measure fidelity
   against the GDELT index for the same queries, and fix the truncation transform.
5. Forward test on the open markets behind the 18 alerts, threshold pre-registered.
6. Contract: an alerts market type (signer pin on `googlealerts-noreply@google.com` and
   the key hash, outlet host allowlist from the result's URL, body profile for the
   quoted-printable HTML part), only after the format census.

## Open items for the owner

- Raise or remove the $1/day limit on the OpenRouter key; rotate it afterwards (it was
  pasted in chat once).
- Decide on a dedicated collection account: the alerts now sit on the owner's personal
  Gmail, which the trust rules say should not be the custodian of evidence.
- A Gmail filter on `from:googlealerts-noreply@google.com` (skip inbox, label) keeps the
  census volume out of the way; not created, since it changes account settings.
