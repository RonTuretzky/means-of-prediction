# Architecture

Markets settle from publicly submitted, RSA-signed newspaper alert headers and authenticated body-source substrings. The app
uses DKIM signature verification and an onchain regex, with an optional existing
LLM-judge path. There is no ZK settlement path, circuit setup or browser SNARK prover.

## Contracts

### `dkim/IDKIMVerifier.sol` and `dkim/DKIMVerifier.sol`

`EmailProof` carries domain, key hash, timestamp, From, exact Subject, optional decoded body
excerpt, nullifier, canonicalized headers and the original signature. The verifier:

1. Reads an authorized key from `DKIMRegistry` and checks its modulus hash.
2. Verifies RSA-SHA256 PKCS#1 v1.5 with the EVM modular-exponentiation precompile.
3. Binds the exact Subject and Date to signed fields through `HeaderParser` and
   requires an exact parsed mailbox match in the unique signed From field.
4. Requires the nullifier to equal the signature hash. An optional body proof supplies the complete canonical body and a bounded byte window; the verifier checks the signed `bh=` hash and decodes the window itself. See [BODY-PARSING.md](BODY-PARSING.md) for the precise profile and limits.

The browser and bot share the parser in `app/src/lib/dkim.ts` and proof builder in
`prover.ts`. Current parsing supports relaxed header canonicalization. The contract
checks the supplied signed bytes, not the entire original RFC 822 message. Body settlement checks the full canonical `bh=` hash and decodes a bounded quoted-printable/identity byte window under the explicit v1 profile. It does not render HTML or implement general MIME extraction.
Signed headers become public calldata, including any recipient fields in the
sender's signed header list. No ZK privacy is claimed.

### `dkim/EmailBodyStore.sol`

Large bodies can be uploaded in <=24,000-byte immutable code pages, with a leading STOP byte. Content hashes deduplicate uploads. A final small transaction supplies ordered page addresses and a compact proof; the store assembles the body and calls the existing market/verifier. Every byte is still authenticated by the original RSA-signed body hash. This preserves onchain verification while adding storage cost; it does not remove final-execution gas limits. See [BODY-PARSING.md](BODY-PARSING.md) for measurements and deployments.

### `dkim/DKIMRegistry.sol`

The deploying address is the fixed registrar. It authenticates domain/selector/RSA
key associations through DNS before registering them. Anyone may read keys or
submit a settlement proof; only the registrar can authorize/revoke keys. Revoked
moduli cannot be registered again. This fixes the old registry's ability to accept
an attacker's key under an arbitrary newspaper's domain.

This is an explicit trust boundary: RSA proves possession of the registered key;
it does not prove DNS ownership. DNSSEC verification, registrar rotation and
historical key-validity windows remain future work. Public demo signing keys must
never be registered in a production registry. Local/Sepolia fixtures use them only
for testing. Existing deployed registries and clones are not changed by this code.

### `lib/RegexLib.sol`

A real onchain matcher parses the supported JS-like regex subset and evaluates it
using NFA position sets. Creation validates patterns; differential tests compare
matching against Node RegExp. There is no circuit compiler or hidden content witness.
Patterns operate over the authenticated subject or decoded body source. Body windows use existential substring rules and reject unescaped whole-input anchors; market creation selects Subject, Body, or SubjectOrBody. Legacy deployment ABI selection keeps old subject-only markets compatible.

### `market/HeadlineMarket.sol`

Each market is its own oracle for a binary condition. Config fixes distinct source
DKIM domains, From patterns, shared/per-source content patterns, K-of-N threshold,
accepted email-date window and settlement buffer. Anyone can submit an accepted
proof. Nullifiers prevent replay within a market. The Kth source resolves YES;
`resolveNo` becomes available after deadline plus buffer. `checkProof` is a view
simulation used before spending gas.

Optional judged markets (criteria plus empty regex) require a YES verdict from the
existing `LLMJudge`. That mechanism has its own pinned model/operator trust model;
see `GASKILLER-LLM-SETTLEMENT.md`. This refactor preserves that separate work.

### `tokens/ConditionalTokens.sol`

Collateral splits into complete YES/NO ERC-1155 sets, merges back, and redeems at the
oracle's final payout vector. Each complete set is backed by one unit of collateral.
The token layer is a simplified CTF-compatible interface, not byte-compatible with
all production Gnosis CTF collection identifiers.

### `market/FPMM.sol` and `market/MarketFactory.sol`

The permissionless factory creates EIP-1167 market/pool clones and optionally funds
the pool for its creator. The pool maintains a binary fixed-product AMM. Quote and
execution paths include both the market's LP fee and the factory's platform fee.

`fee` is the LP rate; `protocolFee` is the platform rate, defaulting to 1% in deploy
scripts. `totalFee` is their sum. Treasury address and platform rate are fixed at
factory deployment and copied to each pool. Platform collateral accrues separately
from LP entitlements. `withdrawProtocolFees` always pays the fixed treasury;
`withdrawFees` pays the entitled LP. Funding, liquidity exits and redemption have no
new platform fee. See `FEES.md` for rounding, constructor options and examples.

Existing clones retain their old implementation/verifier/registry and have no
platform fee. A new deployment is required; this source refactor does not migrate
live markets, balances or positions.

## Private research service

`app/scripts/research/daily.mjs` downloads resolved Polymarket markets from the last
14 days using cursor pagination, and indexes all accessible received email through
read-only IMAP. Raw RFC 822 messages, full-text SQLite index and reports are private
local files outside the public repository. Mailauth verifies signatures/body hashes
offchain. Lexical candidate retrieval is followed by a scheduled Codex semantic
review, with exact email references, source/time checks and explicit pending counts.

Body evidence found in research is not accepted by today's onchain verifier.
Research never creates/trades/settles markets. See `DAILY-RESEARCH.md` and
`EMAIL-ACCESS.md` for setup, schedule, commands and coverage limitations.

## Frontend (`app/`)

Vite + React + TypeScript. UI is [`@breadcoop/ui`](https://github.com/BreadchainCoop/bread-ui-kit)
(bread-ui-kit v2: Tailwind v4 theme import, Pogaca fonts, neo-brutalist Button/Chip/
Typography/Logo) with Polymarket's UX conventions layered on: prices always in cents
with `%` chance as the same number, green YES / red NO everywhere, the trade widget's
"To win $X" hero line, quick-add amount chips, a sacred Rules section (verbatim
criteria + resolver address), status badges, abbreviated volume, and a "You won —
Redeem" claim banner.

- Reads: viem `multicall` (a minimal `Multicall3` is deployed by the script since
  fresh anvil chains lack the canonical one) via react-query, 3s polling. Volume =
  sum of FPMM `Buy`/`Sell` event logs. Time gating uses **chain** time, not wall
  clock, so `evm_increaseTime` behaves.
- Writes: viem wallet clients over anvil's well-known dev accounts with an account
  switcher (real wallet connectors are backlog); every write simulates first for
  readable revert reasons.
- The prover runs **in the browser**: upload a raw `.eml` → parse headers (unfold,
  RFC 2047 subjects, quoted-printable bodies, DKIM `d=`/`b=` tags) → build the
  `EmailProof` → `checkProof` dry-run → submit. The same module powers the
  `prove-email.mjs` CLI.

## Testing

- **Foundry (71 tests)** — regex unit + differential-vs-JS (ffi) + fuzz;
  ConditionalTokens split/merge/report/redeem incl. 50/50 payouts; FPMM funding
  math, hint odds, invariant growth, fee accounting, slippage and resolution guards;
  HeadlineMarket acceptance/rejection matrix (wrong domain, wrong From, non-matching
  content, tampered proof, unregistered domain, out-of-window, replayed nullifier,
  duplicate source, per-source override, Subject-only mode), NO-path timing; two
  full-lifecycle e2e tests with collateral-conservation assertions; custom-collateral
  market.
- **Playwright (9 flows)** — on an isolated anvil+vite pair (ports 8548/5198,
  spawned per run): list/filter/search, faucet + account switch, buy (price impact),
  sell, add liquidity → earn fees → claim, create-market wizard (live regex tester),
  settle via `.eml` upload (non-matching rejected with onchain reason → 2-of-3
  resolves YES → redeem), portfolio, time-warped NO resolution.
