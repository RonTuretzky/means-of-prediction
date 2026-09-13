# Pinned-key markets: snapshot at creation, void on rotation, refund at par

*2026-08-20. Fleshes out the "assume the key stays; if it rotates the market is
void and money comes back" model. Companion to DKIM-PROVENANCE.md (which explores
rotation-FOLLOWING; this explores rotation-ACCEPTING). All rotation data below
measured today: archive.prove.email API + live `dig` verification. Deck:
`pinned-key-markets-deck.html`.*

## 1. The model

At market creation, the creator fetches the sender's current DKIM key (live DoH,
two resolvers; archive consulted only for age evidence) and **pins**
`keccak256(domain · selector · pubkeyDER)` into the market as an immutable term,
alongside a settle-by `expiry`. Traders verify the pin client-side when they
join — joining is consent, exactly like agreeing on any other market term.

- **Settle**: a zk email proof valid under *the pinned hash*, with DKIM `t=` ∈
  [createdAt, expiry], resolves the market. Nothing else can.
- **Void**: if `expiry` passes unresolved, anyone calls `voidMarket()` —
  permissionless, no proof, no oracle. All outcome shares redeem at par
  (YES = NO = 0.5; complete sets = 1.0).

**The central trick: rotation is never proven — it is inferred from absence.**
We don't need an oracle to say "the key died"; we observe that nobody could
prove it lived. The only oracle-shaped moment in the market's life is creation,
and it isn't a protocol oracle at all — it's a market-formation fact each
participant independently checks, like verifying a token address before an LP.

### The surprise security upgrade

Rotation-following registries import the future: if the sender's zone (or its
ESP tenancy) is compromised *after* market creation, the attacker's new key gets
followed into the registry and can settle markets. A pinned market **cannot** be
attacked this way — the pin is fixed and the attacker doesn't hold the pinned
private key. Post-creation compromise of DNS achieves nothing. The attack
surface narrows to: theft of the sender's existing private key (fatal in every
DKIM design), or poisoning the pin *at creation* (mitigated by the age gate,
§4). "Market dies on rotation" is not just a simplification — it buys
compromise immunity for the market's whole lifetime.

## 2. What the rotation data actually says (measured)

### Data honesty first
- Archive `firstSeenAt` is bounded by crawler start (~2024-02) and discovery lag
  (scph20250409, born 2025-04-09 by name, entered the archive 2025-12-16 — 8
  months late). Date-stamped selector names recover true birth dates.
- Archive `lastSeenAt` ≠ death. economist.com's entire fleet reads "dead
  2026-04" in the archive; live dig today shows **all of them still in DNS** —
  the crawler just stopped visiting. Deaths are only real when sibling selectors
  kept being crawled (the NYT April-2025 purge passes this test; verified gone
  by live dig).
- Consequence for the design: **the pin must come from live DNS, never the
  archive**; the archive's job is age/continuity evidence and hazard stats.

### Key lifetimes (archive windows + live verification)
- **irs.gov `irs-20171230`**: one key since 2017 (name-dated), 8.7 years, live.
- **wsj.com `200608`, `dj`, `google`**: RSA-1024 relics, live for the entire
  observation window (2.2y+), no deaths.
- **gmail.com date-stamped chain** (true cadence from names): 20120113 → 20161025
  (4.8y) → 20210112 (4.2y) → 20221208 (1.9y) → 20230601 (0.5y) → 20251104
  (2.4y, Nov 2025). Old and new run concurrently for months–years; old records
  are then **revoked by emptying** (`p=` — live-verified today on 20221208),
  not deleted.
- **nytimes.com April 2025 purge**: six selectors (`scph0118`, `k1`, `200608`,
  `s1`, `smtpapi`, `paperboy-1024`) all removed within Apr 9–17 2025, the same
  week `scph20250409` (RSA-4096) appeared. `k2`, `google`, `ot`, `s2` sailed
  through. Rotations are rare and arrive as **cluster cleanups**.
- **Same-selector re-keying**: `zendesk1`/`zendesk2` re-keyed 3× in 2 years —
  with *identical windows on nytimes.com and washingtonpost.com*, because both
  are CNAMEs to zendesk.com's record: **ESP-fleet-wide rotation**. WSJ's
  `cv-usprod-1` re-keyed ~annually (4 windows). A selector is not a key; the
  pin (a key hash) correctly dies on these; hazard must be scored per key.
- **CNAME ownership**: NYT `k2` → dkim2.mcsv.net (Mailchimp), `kl/kl2` →
  sendgrid.net, `zendesk1/2` → zendesk.com, WaPo tokens → dkim.amazonses.com.
  For CNAME'd selectors **the ESP owns the rotation schedule**, not the sender.
- **Amazon SES (WaPo)**: Easy DKIM auto-rotates keys (AWS docs; reported ~90–365
  days, unannounced). Observed WaPo token windows: 11d / 70d / 283d / 219d.

### Guidance vs practice
M3AAWG best practice says rotate at least twice a year. Measured practice at
major senders: 2–9 years, or never. This gap is why pinning is viable at all.

## 3. Hazard classes → market policy

| Class | Signature | Exemplars (measured) | Naive P(void) per 90d | Policy |
|---|---|---|---|---|
| **A — set-and-forget** | old selector, plain TXT, no date convention | irs-20171230 (8.7y), wsj 200608/dj | ≪3% | pin freely; markets ≤ 1y |
| **B — planned, date-stamped** | YYYYMMDD-style names, cluster cleanups, overlap windows | gmail chain (0.5–4.8y gaps), NYT scph* | ~3–10% | markets ≤ 90d, prefer young keys |
| **C — ESP-fleet re-key via CNAME** | selector CNAMEs into ESP zone; synchronized fleet-wide re-keys | zendesk1 (3× in 2y), cv-usprod-1 (annual) | ~15–30% | markets ≤ 30d, warn loudly |
| **D — auto-rotating tokens** | random-string selectors → dkim.amazonses.com etc. | WaPo SES tokens (11–283d) | ~50%+ | do not pin |

(Naive = duration / mean observed lifetime, uniform hazard; right-censored, so
真 A/B numbers are *better* than shown. Displayed to traders as a rating, not a
false-precision percent.)

## 4. Creation & join flow

1. Creator's client resolves `selector._domainkey.domain` via ≥2 DoH resolvers
   (live), displays the CNAME chain ("who owns your rotation"), computes the pin.
2. **Age gate**: pin only keys with ≥ N months of archive history (default 6).
   Kills fresh dangling-CNAME poisoning and insert-sign-remove games. (The age
   gate is a UI/policy default, not consensus — a market that skips it just gets
   flagged.)
3. The DoH-fetched record bytes go in creation calldata (~500B) as evidence of
   what was claimed.
4. Every client re-verifies the pin against live DNS whenever it renders the
   market; mismatch → red banner. Joining an unverified market is the same trust
   act as buying an unverified token contract — the UI makes verification free.
5. Optional hardening: permissionless bonded "pin-mismatch" flag onchain that
   UIs must surface (no adjudication needed — it's advisory; traders check DNS
   themselves).

## 5. Contract sketch

```solidity
struct Market {
    bytes32 pinnedKeyHash;   // keccak256(domain · selector · pubkey DER)
    uint64  createdAt;
    uint64  expiry;          // settle-by deadline = the void trigger
    // ... AMM state
}

function settle(Groth16Proof calldata p) external {
    require(block.timestamp <= m.expiry,        "past deadline");
    require(p.publicKeyHash == m.pinnedKeyHash, "not the pinned key");
    require(p.dkimTimestamp >= m.createdAt
         && p.dkimTimestamp <= m.expiry,        "t= outside window");
    require(VERIFIER.verify(p),                 "invalid proof");
    _resolve(p.outcome);
}

function voidMarket() external {   // permissionless; no proof, no oracle
    require(block.timestamp > m.expiry && !m.resolved);
    m.mode = Redemption.PAR;       // YES = NO = 0.5; complete set = 1.0
}
```

Replaces the entire DKIMRegistry surface (backlog A2) with one `bytes32` per
market. Keeps the E1 compiled circuit, adding `t=` as a public signal (NYT/
SparkPost mail carries it — verified on the 2020 archived email).

Market classes: **future-event** markets ("will NYT email X before T?") need
`t= ≥ createdAt` — the pinned key must sign a *future* email, so the void hazard
is the signing-switch hazard. **Archival** markets (email already exists at
creation) can settle immediately and carry ~zero rotation risk, but still pin
from live DNS (a key already rotated out can't be pinned trustlessly — that's
DKIM-PROVENANCE.md territory).

## 6. Void economics

- Redemption at par: `V_YES = p·(1−v) + 0.5·v = 0.5 + (p − 0.5)(1 − v)` where
  v = market-implied P(void). Void risk shrinks prices toward 0.5 by (1−v) —
  priced exactly like time value; LPs unwind at par (pool holds complete sets).
- Void transfers value from high-conviction winners to losers (a 0.9-YES holder
  gets 0.5). Acceptable when v is small (class A/B pins) and disclosed.
- Insider wrinkle: someone who knows rotation is scheduled (ESP staff, the
  sender) can buy the sub-0.5 side and harvest the void. Profit bounded by
  |p − 0.5| · stake; mitigations: duration caps, class gates, and the fact that
  cluster-cleanup rotations (NYT-style) are observable in advance by anyone
  watching DNS (new selector appears → overlap window opens).
- Alternative future work: tradeable VOID outcome token (Augur-style invalid
  share) so rotation risk gets its own price instead of distorting YES/NO.

## 7. What this deletes, what it costs

**Deletes**: DKIMRegistry, updater committee, rotation-following, witnessed-log
*as a trust component* (it survives as the hazard-stats + age-evidence dataset),
DNSSEC dependency for the happy path.

**Costs**: markets are short (class-capped); SES-class senders are effectively
unpinnable; void is a real outcome traders must price; non-verifying traders
are exposed to a malicious pin (UI auto-verification is the mitigation, and the
worst honest-participant outcome is par refund, not theft); no market can span
a planned rotation even when the rotation is benign.

## 8. The honest one-liner

The market doesn't outlive the key. It agrees on the key at birth — a fact every
participant can check for free — prices the key's death like time value, and
dies gracefully into refunds if the key dies first. No committee ever exists.
