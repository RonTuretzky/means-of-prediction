# Dataset v2: reporting-admissible markets and timestamped news evidence

Written September 16, 2026, after the Fable generator and judge swaps.

## Why the current set cannot answer the settlement question

The development set is 161 reviewed market/email pairs drawn from 143 NYT
newsletter emails. Under each market's own fine print, exactly one pair is
answerable: market 3709179, "Duane Keith Davis convicted of Tupac's murder?",
whose rules accept reporting of a conviction. The other 160 markets demand an
official source or a detail the newsletter lacks. So the set measures
fact recovery well and settlement almost not at all, and no amount of prompt
optimization changes that. The generator and judge swaps proved the AI side
is not the constraint (Fable as judge: 149 of 160 facts with an exact quote,
zero false positives on 237 decoys); the evidence set is.

## What the catalog says

Of the 3.3 million catalog markets, 1,397,747 have rules that settle on
"credible reporting", where a newspaper report is admissible. Restricting to
markets that resolved decisively between June 2025 and September 2026 and
dropping sports matches and props, crypto price ticks and every held-out or
reserved market leaves a pool of **63,368 markets** with a private payout
record (`~/.local/share/means-of-prediction/dataset-v2-20260916/market-pool-v2`,
built by `app/scripts/research/dataset_v2/build_market_pool.py`; the first
`market-pool` directory used a looser sports filter and is superseded).
Topic buckets by keyword: 30,976 sports season or award questions, 22,295
other news-shaped questions (still containing chess, esports and golf props
alongside real news such as arrests and leadership changes), 3,627
geopolitics, 2,773 elections, 1,587 entertainment, 1,511 science and tech,
415 business, 155 courts, 29 weather. Of the 1,217,155 distinct
credible-reporting markets in the window, 1,122,667 were sports matches or
props. The keyword buckets are coarse and will be refined at pairing time.

## What the mailbox says

The mailbox holds 19,408 emails back to 2008, but only 1,597 since September
2025, and the only newspaper among them is The New York Times (132). The
DKIM registry can already verify 97 outlets, including AP, Reuters, AFP,
BBC, The Guardian, Washington Post and CNN, none of which the mailbox is
subscribed to. Evidence, not markets, is the bottleneck.

## Design

1. **Markets.** The pool above, deduplicated by event group, stratified by
   topic and month. Payouts stay private observations.
2. **Evidence, three sources.**
   - *Guardian Open Platform.* Full article body text under a free
     non-commercial developer key, timestamped, licensed. The first
     full-text corpus this project would have. Needs a key.
   - *NYT Article Search and Archive.* Headline, abstract, lead paragraph,
     byline, date. Metadata only, but it carries core facts. Needs a key.
   - *Newsletter subscriptions.* Subscribe the research mailbox to the
     outlets in `docs/NEWSLETTER-SUBSCRIPTIONS.md`. This is the only source
     the deployed contract can settle from (DKIM-signed), and it accrues
     prospectively, so it starts now and pays off over weeks.
3. **Pairing.** A local full-text index over evidence (FTS5) queried with
   entities and dates from each market's question; date window from market
   creation to resolution plus two days; candidate pairs ranked and capped
   per market. Unmatched markets are retained as coverage observations.
4. **Labels, two layers.**
   - *Payout consistency at scale.* The blind judge (rule plus one
     document) makes a claim; a YES claim on a market that resolved NO is a
     definite false claim. Across tens of thousands of pairs this gives a
     cheap precision floor and a coverage curve without any human labels.
     Agreement with a payout is never treated as proof the document
     settles the market.
   - *Answerability review.* A stratified sample (by topic, outlet, and
     claim status) reviewed by two independent models for answerability
     under the original rules, with a sealed human-checked holdout. Same
     procedure that produced the 161 labels, applied to a set where most
     markets accept reporting.
5. **Metrics with their own denominators.** Coverage: markets with at least
   one candidate document. Claim precision against payouts. Grounded
   recall on reviewed positives. Answerability rate under original rules.
   Reported per source and per topic, never pooled with the email 161.
6. **Splits.** Grouped by event family and month, sealed before any judge
   call; a time-forward holdout (latest month) for the prospective claim.

## Status

- Market pool: built.
- Guardian and NYT keys: needed from the user (`~/.config/means-of-prediction/guardian.json` and `nyt.json` as `{"apiKey": "..."}`).
- Newsletter subscriptions: needed from the user (mailbox side).
- Retrieval index, pairing, payout-consistency scoring, review sampler: next code, buildable before the keys arrive against the existing 143 NYT emails.
