# Research plan v2: from "can an AI read the email" to "can a market settle on it"

September 17, 2026. Supersedes the prompt-optimization loop, which was stopped
on September 16 at the user's request. This version incorporates an
adversarial review by three independent critics (settlement security,
research method, feasibility); their findings changed the threat model, the
gates, the first experiments and the rule template.

## What we learned

1. A frontier reader is good enough. Claude Fable 5.1 judging whole
   newsletter emails recovered 149 of 160 known facts with an exact quote,
   with zero false claims on 237 negative controls and zero claims on 115
   weak or unrelated emails.
2. The reader the chain can trust is not. The local Qwen3.5-35B-A3B, the
   model class the Gas Killer design can re-execute verifiably
   (`docs/GASKILLER-LLM-SETTLEMENT.md`), recovered 65 of 160 on the same
   whole emails and made 19 unjustified claims.
3. *Hypothesis, tested once and not supported in its simple form:* that the
   small model's weakness is finding the sentence rather than judging it.
   Given only the passage the frontier model located (same rule, prompt and
   scorer), the small judge found fewer facts, 45 of 160 grounded against
   65 on whole emails, while its false claims fell to zero (0 of 237
   negatives, 0 of 115 weak or unrelated, from 2 and 19). On the 150
   located factual passages it was right 52 times, answered "neither" 31
   times, and answered "both outcomes conflict" 65 times. Its dominant
   failure is the five-field A-versus-B judgment format, which is also not
   the format the chain would run. The follow-up asks one constrained
   YES/NO per claim on the same passages.
4. Our yardstick was wrong for the product. "Answerable under Polymarket's
   original rules" (1 of 161) grades emails against fine print a market we
   author would not contain.
5. Evidence is the scarce input. 1.4 million catalog markets settle on
   "credible reporting" and 63,368 non-sports ones have recorded payouts,
   but the mailbox receives newsletters from one outlet.
6. *New, from the review:* a valid DKIM signature proves the outlet's
   domain signed the bytes, not that the newsroom wrote them. The key
   registry includes corporate mail keys, support-desk keys that echo a
   requester's own text, transactional keys, and 286 RSA-1024 keys. "97
   verifiable outlets" overstates the admissible evidence base.
7. *New:* in the development set only 19 of 161 facts arrived before the
   market closed. Morning briefings are late; the timely carrier for
   scheduled events is the breaking-news alert, where the fact is in the
   Subject line, the headline-sized case the on-chain judge already handles.

## Exploratory results, September 17 (local, free, not pre-registered)

Three quick runs on the 730-row judge-swap subset, all with the local
Qwen3.5-35B-A3B and the frontier model's located passages (300 characters
of context each side). They are exploratory and shape the plan; none is a
gate result.

| Run | What the small judge was asked | Facts found | False claims |
|---|---|---:|---:|
| Whole email (baseline) | five-field A/B judgment on the full email | 65 of 160 | 21 |
| 1a | same judgment, located passage only | 45 of 160 | 0 |
| 1b | one constrained YES/NO per generated claim | 11 of 161 | 0 |
| 1c | one constrained YES/NO, claim = the market's own question, yes/no markets only | 2 of 35 true-YES facts; 0 of 63 positive controls | 0 on 81 true-NO facts, 170 empty controls, 100 weak or unrelated |

The harness itself is sound: trivial declarative cases are answered
correctly in under a second. What the runs say:

- **Locating alone does not rescue the small judge.** In the five-field
  format it answers "both outcomes conflict" on 65 of 150 located passages.
- **In the verifiable call shape it is safe and nearly useless** with naive
  criteria. The generated claims are long (median 425 characters, packed
  with roles, dates and exceptions) and a strict judge answers NO unless
  every clause is established; question-form claims fare no better.
- **Most of our known facts are "No" outcomes**: 81 of the 116 yes/no
  facts. Newspapers report what happened, not what did not, so a
  YES-only email settlement cannot prove them directly.

Consequences adopted below: the verifiable judge needs a short declarative
criterion authored with the market, a calibrated on-chain prompt measured
on real passages, and probably distillation; Subject-first gains priority;
and "No" must settle through **exclusivity groups** (the winner's market
settles YES from an email, its mutually exclusive siblings settle NO by
construction) or by deadline void, never by asking a model to prove a
negative.

## The question

> Can a prediction market settle automatically, correctly and verifiably from
> DKIM-signed newspaper emails: for which events, how fast, and at what
> per-market error rate against someone trying to cheat?

| Unknown | Why it decides the product | How we will know |
|---|---|---|
| **Admissible evidence** | Signed is not the same as editorial | Per outlet: which selector, From mailbox and key size real newsletters use, and whether they fit the contract's body profile |
| **Coverage and timing** | No timely email, no settlement | Lag from event to email, Subject-carried or body-only, per event type and outlet |
| **Verifiable reading** | The chain cannot trust a hosted model's say-so | Per-market false settlement under a best-of-N submitter, and a staged recall funnel |
| **Rule design** | Ambiguous rules turn good reading into disputes | Disagreement between independent judges on authored markets |

## Threat model (new)

Attackers: a YES holder, a NO holder, the settlement bot's operator, the
judge fleet's operators, outlet staff, and the outlet's email vendor.
Submission is permissionless and a rejected attempt costs the attacker almost
nothing, so the money number is **false settlement per market over its whole
window against a best-of-N submitter**, with the number of required distinct
outlets K stated. Per-excerpt error rates are diagnostics only: at a 2%
per-email error and 50 topical emails, a false YES is 64% likely.
Consequences adopted throughout: markets list their sources as (signing
domain, selector key hash, From mailbox pattern) taken from observed
newsletter sends; corporate, support-desk, transactional and RSA-1024 keys
are inadmissible for judged markets; K is at least 2 outlets; a YES becomes
final only after a challenge delay; the deadline default is VOID with a par
refund, not NO.

## Track 0: free censuses before any model call (days 1–3)

CPU only, no hosted usage, and each one can kill or reshape a later track.

- **Provability and budget census.** For each of the 149 located quotes:
  does one contiguous window of the DKIM-canonical body source (at most
  4,096 bytes, the contract's limit) contain it; does the email fit the v1
  body profile; how many judge tokens is the window; what gas and hours per
  verdict does that imply; is the fact also in the Subject.
- **Timing census.** For the 161 known facts: lag from event or market close
  to email receipt, alert versus briefing, Subject-carried versus body-only.
- **Admissible-source census.** For every outlet with observed newsletter
  sends: selector, From mailbox, List-Id, key size, MIME shape. Publish the
  count of outlets that remain admissible. That count is the evidence base.
- **Regex fallback, made real.** Commit the 480-headline adversarial corpus
  as contract test fixtures with a differential test, and tighten the
  patterns until false YES on the corpus is at most 3. This is the only
  settlement path with no external dependency.

## Track 1: Subject-first verifiable judging (the shippable path)

The on-chain judge today binds only the signed Subject, in a single-token
YES/NO decode with a pinned template. Measure exactly that call shape, not
the LM Studio JSON harness: breaking-news Subjects against authored
criteria, with an integer-engine parity check on at least 300 rows.
**Slice S1, by day 14 and independent of everything else:** three authored
Sepolia Subject markets with K-of-N admissible sources, settled by regex
with the judge in shadow mode.

## Track 2: locate, then judge (the research path)

**Idea.** An untrusted frontier model only *locates* an excerpt of the signed
body; the small verifiable model *judges* the excerpt against the criterion.
Excerpts are defined on bytes the contract can prove, and every excerpt
policy under test is a contract-checkable predicate (window boundaries,
markup stripping, minimum length, contract-extended context). The judge
prompt is assembled from the signed Date, signed Subject and the excerpt,
never the excerpt alone.

**Measured as a funnel, each stage with its own denominator:** rule
available; locator excerpt contains the fact; excerpt maps to one provable
window; judge verdict correct given the excerpt. The judge is not asked to
quote.

**Experiments, cheapest first.**

1. *Recall replays with located quotes* (three exploratory runs done
   September 17, table above). Next, pre-registered: author a short
   declarative criterion per market side (one event, one entity, dated
   instance, at most about 120 characters), calibrate the judge prompt in
   the true on-chain template on a held-out half of the passages, and
   report recall on the other half. Measures recall only. Control arms
   on the same rows: claim with no excerpt (any YES is memory, not
   reading), a random sentence, BM25 top sentences as a non-LLM locator,
   Subject only, and a counterfactual excerpt with the entity swapped.
2. *Forced-excerpt false-YES sweep* (local, about a day). On the negative
   controls and weak emails, slide every provable window containing an
   entity from the question through the judge in the on-chain call shape.
   The false-claim rate is the share of market-emails with any YES-yielding
   window. This is the number the first replay cannot produce, because an
   honest locator abstains and an attacker never does.
3. *Adversarial locator with a fixed attack taxonomy*, at least 50 real-email
   instances per class: stale or recap events, sibling entity or wrong
   office, opinion and satire, forecasts and odds, quoted claims, denials,
   hidden markup text.
4. *Judge ladder and excerpt budget*: 4B, 8B, 35B-A3B at 64 to 512 tokens,
   priced in gas and hours per verdict.
5. *Only if the above fall short:* distil the small judge on frontier
   judgments, with new pinned weights. Student candidates include small
   single-pass encoders such as Laya (421M, deterministic, about 21 ms per
   call); out of the box it cannot separate true from false on our rows
   (`docs/LAYA-BENCHMARK-20260921.md`), so it is a fine-tuning target, not
   a drop-in judge.

## Track 3: evidence

- **Subscribe a dedicated research mailbox** to the priority outlets in
  `docs/NEWSLETTER-SUBSCRIPTIONS.md`, alerts as well as briefings. Dedicated
  because a body proof publishes the full body and signed headers on-chain,
  including the recipient address and personalised links; paywalled
  newsletters need an explicit publication decision.
- **Backfill proxies** for coverage estimates only: Guardian full text and
  NYT Article Search metadata (free keys).
- **Payout and timing consistency** on the 63,368-market pool, two flags: a
  YES claim on a NO-resolved market, and a YES claim from a document dated
  before the event could have occurred. A human audits 200 flagged and 300
  unflagged claims, stratified by topic and outlet. Agreement with a payout
  is never proof.

## Track 4: a pre-registered forward test

The only experiment immune to "the model remembers the news". Three strata,
frozen and hashed before the events: **A**, 120 authored markets on
scheduled events one to four weeks ahead; **B**, 120 unscheduled by-date
markets drawn at random from open credible-reporting markets and re-ruled
with the template; **C**, for every event, at least two mutually exclusive
or near-miss sibling markets, so at least half of all markets are truth-NO
with entity-matching coverage. Every settlement is tagged Subject-carried or
body-only. Until a judged pipeline exists on-chain this is an off-chain
simulation and is labelled as one.

**Negatives settle by structure, not by evidence.** Markets are authored in
mutually exclusive groups where the reportable event is always a YES side;
a sibling's final YES settles the others NO. Standalone "will X happen by
T" markets void at par when no YES becomes final.

**Rule template under test.** "Resolves YES when emails from at least K
listed sources, received between T0 and T1, each state as a completed fact
that X, where X names the dated event instance. Forecasts, projections,
odds, quoted claims by interested parties and conditional statements do not
count. A YES becomes final after a 48-hour challenge delay, during which a
later email from the same source judged to retract it cancels that proof.
If no YES is final by T1 plus 7 days the market resolves VOID at par.
NO-by-evidence is out of scope until separately measured."

## Gates

**G1, week 2.** On the 693 rows both judges completed, plus the sweep:
funnel stages reported; locate-then-judge recall with the 35B-A3B judge at
least 90% of the frontier's; at most 1% of negative market-emails have any
YES-yielding window under the single pre-registered excerpt policy. If the
interval straddles a threshold, run the confirmatory repeat once; if it
fails, go to distillation or fall back to Subject-only scope.

**G2, week 8, interim read at week 5.** Decides on coverage within 48 hours
per event type (about 30 markets each, roughly ±17 points). Pooled false
settlements are reported with an exact interval and cannot support a 0.5%
claim; that target belongs to the sweep and the audited payout arm, each
sized to at least 600 negative market-level trials, where zero failures
bounds the rate near 0.5%. **Decision rule:** if at least 70% of
within-48-hour settlements are Subject-carried, ship Subject-judged markets
first and keep locate-then-judge as research.

All primary metrics, the excerpt policy, interval methods and stopping rules
are pre-registered in a hashed file before any Track 2 run; everything else
is labelled exploratory.

## Stop, keep

**Stop:** the prompt-optimization loop on the 161-pair set; "answerable under
Polymarket rules" as a headline metric; pursuit of NYT article text through
blocked routes; treating a hosted frontier judge as the arbiter.
**Keep:** the regex path as the deterministic fallback, now with a test
corpus; the Fable transport, judge arm and receipts discipline; all sealed
evaluation reservations, unopened.

## Sequence

| When | Work | Output |
|---|---|---|
| Days 1–3 | Track 0 censuses; regex fixtures and fixes; recall replay and controls; pre-registration file; user starts the dedicated mailbox and subscriptions | Go or no-go on body excerpts; admissible outlet count; first recall number |
| Days 4–14 | Forced-excerpt sweep; on-chain-shape Subject harness with integer parity; adversarial taxonomy; freeze the forward-test strata; **slice S1 on Sepolia** | G1; frozen market list; three live Subject markets |
| Weeks 3–8 | Forward test on arriving emails; payout and timing audit; judge ladder; distillation only if G1 failed | Interim read week 5; G2 week 8 |
| After G2 | Sepolia prototype of the winning mode beside the substring rules | Product scope per event type |

## Costs, dependencies, risks

| Job | Rows | List cost at about $0.17 per hosted row | Limit waits | Where |
|---|---:|---:|---:|---|
| Track 0 censuses, regex fixtures | — | $0 | 0 | CPU |
| Recall replay, sweep, Subject harness, ladder | tens of thousands of short calls | $0 | 0 | local judge |
| Adversarial locator | about 1,500 | about $250 | about 15 | hosted, batched |
| Payout-arm claims on the pool | 10,000 | about $1,700 | about 100 | hosted, batched over weeks |

Hosted work is batched and never depends on a live chat session; the sign-in
paused runs three times on September 16. **Dependencies with no owner yet:**
the Gas Killer fleet for any judged on-chain prototype (sharded 35B, overlay
mounting, ingress key; all open upstream), registrar registration of
observed newsletter keys on the Sepolia registry (it holds 4 NYT keys), the
settlement worker's NYT-only scope, and multipart or base64 support in the
body parser. **If the user-side inputs slip** (mailbox, subscriptions,
keys): Tracks 0, 1 and the local part of Track 2 proceed unchanged; Track 4
shrinks to the outlets available and its start date moves, never its
pre-registration.
