# Means of Prediction — markets settled by the newspapers themselves

*(formerly "Headlines")*

Binary prediction markets where **settlement is a public DKIM signature proof of a newspaper
breaking-news alert email**. Anyone can permissionlessly:

- **open a market** over any set of newspapers, any regex condition, any ERC-20
  collateral token, and
- **settle a market** by submitting a proof of a matching alert email (or resolve
  NO after the deadline).

The token layer reimplements the Conditional Tokens model Polymarket settles on;
trading runs through a Gnosis-style fixed-product AMM (Polymarket's original venue).
Settlement is **real DKIM verification**: an email's RSA-SHA256 signature is checked
onchain (modexp precompile) against a key whose domain association is authenticated
by the deployment registrar —
the same RSA operation used in DKIM verification. The new Sepolia deployment also authenticates complete body hashes and bounded body-text witnesses; see [body parsing](docs/BODY-PARSING.md).

A dedicated [automatic email settlement worker](docs/AUTO-SETTLEMENT.md) now collects authenticated NYT mail and submits accepted Subject/body proofs on the new Sepolia deployment. It uses a durable encrypted journal and a separate restricted signer. The existing Gnosis deployment remains unchanged.

```
┌─────────────┐   creates    ┌────────────────┐   oracle-reports   ┌───────────────────┐
│MarketFactory├─────────────▶│ HeadlineMarket │───────────────────▶│ ConditionalTokens │
└─────────────┘              │  (the oracle)  │    [1,0] / [0,1]   │  (CTF-style 1155) │
                             └───▲────────────┘                    └─────────▲─────────┘
                                 │ submitProof(EmailProof)                   │ split/merge/redeem
                          ┌──────┴───────────┐                     ┌─────────┴─────────┐
                          │  DKIMVerifier    │                    │       FPMM        │
                          │ +  DKIMRegistry   │                    │ (YES/NO AMM pool) │
                          └──────────────────┘                     └───────────────────┘
```

## Live on Gnosis mainnet (chain 100)

**App: https://ronturetzky.github.io/means-of-prediction/** — a static GitHub Pages
bundle (no backend) that auto-indexes the deployment from
`contracts/deployments/gnosis.json`, reads markets live from Gnosis, and connects an
injected wallet to trade/settle. Rebuilt + redeployed by `.github/workflows/pages.yml`
on every push (same crowdstake.fun pattern).


Deployed 2026-08-21, **all contracts verified** on [gnosisscan.io](https://gnosisscan.io) (Blockscout):

| Contract | Address |
|---|---|
| MarketFactory | [`0xEb6dedbf1BCE0B0D60e7f807304AEA680925baA9`](https://gnosisscan.io/address/0xEb6dedbf1BCE0B0D60e7f807304AEA680925baA9) |
| ConditionalTokens | [`0x47CCC3b9e5A531f4cC30D0D6709C4aaD429F0f78`](https://gnosisscan.io/address/0x47CCC3b9e5A531f4cC30D0D6709C4aaD429F0f78) |
| DKIMRegistry | [`0x548427E025deBC88d816B37717002f1afD1c1E62`](https://gnosisscan.io/address/0x548427E025deBC88d816B37717002f1afD1c1E62) |
| DKIMVerifier | [`0x353eA8FF93D818E878b14451D657938DF4B00c1A`](https://gnosisscan.io/address/0x353eA8FF93D818E878b14451D657938DF4B00c1A) |
| HeadlineMarket impl | [`0x38570fca07b23ca49807d4456ce92eF042E87e8c`](https://gnosisscan.io/address/0x38570fca07b23ca49807d4456ce92eF042E87e8c) |
| FPMM impl | [`0xaD0f94e49A9BE09257A99497EE8B573E379e4fCC`](https://gnosisscan.io/address/0xaD0f94e49A9BE09257A99497EE8B573E379e4fCC) |
| First market ("Fed rate cut by October 2026?") | [`0x7024A123019CB2E83c168D37B0C7866e1b221C67`](https://gnosisscan.io/address/0x7024A123019CB2E83c168D37B0C7866e1b221C67) |

- Collateral: any ERC-20 — the app offers **WXDAI, USDC, USDC.e, sDAI, EURe** (all
  onchain-verified addresses) on Gnosis; the first market is seeded in WXDAI.
- **~560 real newspaper DKIM keys** (97 outlets — see [docs/DKIM-KEYS.md](docs/DKIM-KEYS.md),
  discovered via the ZK Email archive + live DNS) are registered in the mainnet
  DKIMRegistry, so a genuine alert from any of them verifies onchain. The throwaway
  demo key is **revoked** on mainnet; audit everything in the registry's events.
- Run the app against mainnet: `cd app && pnpm build:gnosis` (or `DEPLOYMENT=gnosis
  pnpm sync && pnpm dev`); connect an injected wallet (MetaMask/Rabby) — the local
  faucet/dev accounts appear only on anvil.
- CI/CD via [etherform](https://github.com/BreadchainCoop/etherform):
  `.github/workflows/cicd.yml` runs build/test on every PR and deploys
  `script/DeployGnosis.s.sol` with Blockscout verification (repo secrets
  `PRIVATE_KEY` + `RPC_URL`). `contracts/script/verify-blockscout.mjs` re-verifies a
  manual deploy.

### The board: Polymarket's top-50, ported

The Gnosis deployment carries **40 live markets ported from Polymarket's top-50 by
volume** (evaluated 2026-08-21). A multi-agent pipeline judged each market's
*email-settleability* — would K distinct newspapers near-certainly send a breaking-alert
email whose subject a RegexLib pattern catches, with no false positives from
speculation/negation headlines? — then adversarially reviewed every draft regex
(compile-tested, positive/negative subject fixtures) before creation. ~10 of the top 50
(Ethiopian PM succession, "aliens confirmed", "Jesus returns", exact-number props) were
rejected as not email-settleable; the rest are live with `[category:x]` tags and **zero
initial liquidity** — fund one from its Liquidity panel (you set the opening odds) and
trading opens. Creation configs: `app/scripts/create-markets.mjs`.

### Settlement bot (daily cron)

`app/scripts/settlement-bot.mjs` makes settlement automatic: it reads a mailbox over
IMAP (or `.eml` files), parses each newspaper email's real DKIM signature, matches it
against every unresolved market (domain, From-regex, content regex, time window — the
same checks the contract makes), dry-runs `checkProof`, and submits `submitProof` for
every accepted pair; it also calls `resolveNo` on markets past deadline + buffer. If a
sender's key `(domain, selector)` isn't registered yet, it's looked up in the registry's
events, then fetched from DNS and registered by the authorized registrar. New keys
must be authorized before they can settle a market. `.github/workflows/settle.yml` runs it **daily at 13:17 UTC** (and on
demand, with a dry-run switch). To run the experiment, set three repo secrets yourself:
`GMAIL_USER` (a mailbox subscribed to the papers' breaking-news alerts — a dedicated
account is wise), `GMAIL_APP_PASSWORD` (Google Account → Security → 2-Step Verification
→ App passwords; IMAP enabled), and `PRIVATE_KEY` (a funded settler key). Locally:

```bash
cd app && GMAIL_USER=… GMAIL_APP_PASSWORD=… node scripts/settlement-bot.mjs --network gnosis --since 2d   # dry run without PRIVATE_KEY
node scripts/settlement-bot.mjs --network sepolia --eml ../emails/nyt-fed-cut.eml --eml ../emails/wapo-fed-cut.eml  # fixture settlement
```

> **Mainnet key hygiene:** the committed demo DKIM key was **revoked on Gnosis for all
> eight newspaper domains on 2026-08-21** (registrant-only `revokeKey`), so the sample
> fixtures can no longer settle mainnet markets. Only the real `nytimes.com` key is
> registered there; other papers' real keys are registered by the bot from DNS when
> their first genuine alert arrives. Fixtures still settle markets on local anvil and Sepolia.

## Also live on Sepolia testnet (chain 11155111)

Same stack, free to try: faucet **TestUSDC** collateral, the demo DKIM key **and the real
NYT key** registered, two seeded markets (the Fed-cut market settles with the sample
`.eml` fixtures) **plus the same 40 Polymarket-ported markets as mainnet**. Switch networks from the header dropdown on the live app — the static
bundle embeds every deployment and picks via `localStorage`.

All contracts verified on [eth-sepolia.blockscout.com](https://eth-sepolia.blockscout.com):

| Contract | Address |
|---|---|
| MarketFactory | [`0x534bf057b115Ca133C982f42acDB3Fc8fe8B3b4b`](https://eth-sepolia.blockscout.com/address/0x534bf057b115Ca133C982f42acDB3Fc8fe8B3b4b) |
| ConditionalTokens | [`0x583f520E35BDA4caFeEa7d7a3b2f358d838789a5`](https://eth-sepolia.blockscout.com/address/0x583f520E35BDA4caFeEa7d7a3b2f358d838789a5) |
| DKIMRegistry | [`0xE8803065fA3eAa9aE82A839028a09535799e2ff7`](https://eth-sepolia.blockscout.com/address/0xE8803065fA3eAa9aE82A839028a09535799e2ff7) |
| DKIMVerifier | [`0x9fb26E84e98030bFc523ae60f5660B3287aEF2dB`](https://eth-sepolia.blockscout.com/address/0x9fb26E84e98030bFc523ae60f5660B3287aEF2dB) |
| TestUSDC (faucet) | [`0x0A29a562a2141b3bB209bDa1F53A1fC65DAB0742`](https://eth-sepolia.blockscout.com/address/0x0A29a562a2141b3bB209bDa1F53A1fC65DAB0742) |

Deploy your own: `node ../app/scripts/dkim-keys.mjs && forge script
script/DeploySepolia.s.sol:DeploySepolia --rpc-url $RPC --broadcast --private-key $PK`,
then `node script/verify-blockscout.mjs sepolia`. CI (`cicd.yml`) deploys this script on
PRs via etherform with the repo's `PRIVATE_KEY`/`RPC_URL` secrets (Sepolia); the Gnosis
mainnet deploy stays manual.

## See it in action

**Browse & trade** — market cards with live sparklines, a price-history chart with crosshair, and the Polymarket-style buy widget ("To win $X").

![browse and trade](docs/assets/browse-and-trade.gif)

**Open a market, permissionlessly** — pick newspapers and a Polymarket-style category, then write the condition three ways: **plain words**, raw **regex**, or **AI** — describe the condition in English and an LLM running entirely in your browser (Chrome's built-in model, else WebLLM on WebGPU) writes a long subset-safe regex, lint-checked, compiled and tested against your example headlines before it's accepted.

![create a market](docs/assets/create-market.gif)

**Settle with a real DKIM proof** — upload a signed `.eml`; its RSA-SHA256 signature is verified onchain against the newspaper's published key; the 2-of-3 threshold resolves the market YES.

![settle with a real DKIM proof](docs/assets/settle-dkim.gif)

## Repo layout

| Path | What |
|---|---|
| `contracts/` | Foundry project: RegexLib, ConditionalTokens, HeadlineMarket, FPMM, EIP-1167 factory, **real DKIM verification** (RSAVerify + DKIMRegistry + DKIMVerifier), 75-test suite |
| `app/` | Vite + React frontend built with [`@breadcoop/ui`](https://github.com/BreadchainCoop/bread-ui-kit) (bread-ui-kit), viem, Playwright e2e |
| `emails/` | Sample `.eml` files, DKIM-signed by the committed dev key (`pnpm dkim:sign-fixtures`) |
| `docs/` | [Architecture](docs/ARCHITECTURE.md) · [User flows](docs/USER-FLOWS.md) · [Newspapers](docs/NEWSPAPERS.md) · [Polymarket-parity backlog](docs/BACKLOG.md) |

## Quickstart

Prereqs: [Foundry](https://getfoundry.sh), Node 22+, pnpm.

```bash
# 1. chain (vanilla anvil works: every contract is under EIP-170 and settlement
#    uses the public RSA/DKIM verifier)
anvil --port 8547

# 2. contracts — deploys the stack + 3 seeded demo markets, writes deployments/local.json
cd contracts
forge script script/Deploy.s.sol:Deploy --rpc-url http://localhost:8547 --broadcast \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

# 3. app — syncs ABIs/addresses then serves on http://localhost:5199
cd ../app && pnpm install && pnpm dev
```

The header has a **faucet** (test USDC) and a **dev-account switcher** (Alice/Bob/Carol
= anvil's well-known accounts). To settle the seeded "Fed rate cut" market, open it and
upload `emails/nyt-fed-cut.eml`, then `emails/wapo-fed-cut.eml` — the second accepted
proof reaches the 2-of-3 threshold and resolves YES.

### Tests

```bash
cd contracts && forge test        # real RSA/DKIM, registry access, fee accounting, regex, CTF and lifecycle tests
cd app && pnpm e2e                # 9 Playwright flows on an isolated anvil (port 8548)
```

### Email coverage research and revenue

- [Connect your mailbox and enable settlement](docs/EMAIL-ACCESS.md).
- [Daily Polymarket/email retrospective research](docs/DAILY-RESEARCH.md).
- [NYT-specific Astra prompt optimization and blind rule generation](docs/BLIND-NYT-PROMPT-RESEARCH.md).
- [Blind generator transport: Claude Fable 5.1 replaces Astra](docs/FABLE-GENERATOR-TRANSPORT.md).
- [Fable round 1: autonomous prose-rule / local-Qwen improvement loop](docs/FABLE-ROUND-20260915.md).
- [Slides: the running Fable research loop](docs/fable-loop-deck.html).
- [Platform fee configuration and collection](docs/FEES.md).

The unused ZK circuit experiment and its dependencies have been removed. Settlement
requires no proving circuit, trusted setup or redaction. Signed headers are public
calldata. Historical ZK research remains in the documentation as a record only.

## How settlement works

A market is configured at creation with:

- **sources** — up to 32 newspapers, each `{name, dkimDomain, fromRegex, contentRegex?}`,
- **contentRegex** — the headline condition, evaluated *onchain* by `RegexLib`
  (subset of JS regex: literals, `. * + ? {m,n}`, classes, groups, alternation,
  anchors, `\d \w \s`, `(?i)`); per-source overrides supported since papers word
  headlines differently,
- **contentField** — use subject; body evidence is refused until onchain body-hash verification is implemented,
- **threshold K** — distinct newspapers required for YES (aggregate settlement),
- **window / deadline / buffer** — accepted email `Date` range; after
  `deadline + buffer` anyone can resolve NO.

`submitProof(sourceIndex, EmailProof)` — the proof carries the email's canonicalized
signed headers + its real RSA signature. Onchain, `DKIMVerifier`:
1. looks up the sending domain's RSA public key in `DKIMRegistry` (real DNS keys),
2. verifies the RSA-SHA256 signature over the header bytes (`RSAVerify` + the modexp
   precompile) — genuine DKIM verification, and
3. binds From, exact Subject and Date to authenticated header fields and refuses
   nonempty body excerpts.
The market then runs its regex (onchain `RegexLib`) over the **DKIM-verified Subject**,
dedupes by email nullifier, and marks the source. The K-th distinct source reports
payout `[1,0]` to ConditionalTokens; `resolveNo()` reports `[0,1]` after deadline +
buffer. The market contract *is* the oracle — no human, committee, or mock in the loop.

## Market token management

Follows the Polymarket/Gnosis standard:

- Each market is a 2-slot **condition**; YES/NO are ERC-1155 positions fully
  collateralised by the market's ERC-20 (`splitPosition` 1 → 1 YES + 1 NO,
  `mergePositions` back, `redeemPositions` at the reported payout after resolution).
- **Collateral is configurable per market** (test USDC by default; the e2e suite also
  exercises an 18-decimal token).
- Trading via a per-market **FPMM**: constant-product AMM over the YES/NO pool,
  configurable LP fee plus a fixed platform fee (default 1% for new deployments);
  `distributionHint` sets opening odds.
  Prices are probabilities — displayed in cents, Polymarket-style.

## Trust model — what's real, what's assumed

| Component | Here | Production delta |
|---|---|---|
| Email authenticity | **REAL** DKIM: RSA-SHA256 verified onchain (`RSAVerify` + modexp) against the domain's real public key in `DKIMRegistry`. The real NYT key + a real NYT email verify end to end. | Registrar authenticates DNS keys; DNSSEC and historical validity windows remain future work (A2). |
| Test fixtures | The sample `.eml`s are signed by a **real** committed dev RSA key (`keys/dev-dkim.pub`) — real signatures, real verification, dev key (we can't hold NYT's private key). Registered on local/Sepolia only; **revoked on Gnosis mainnet**. | Real senders sign their own real emails; the authorized registrar registers their DNS keys. |
| Regex | **REAL** onchain matcher (`RegexLib`) over the DKIM-verified Subject. | No circuit required; improve authenticated body and numeric condition support. |
| Tokens / AMM / factory | **REAL** ConditionalTokens, FPMM, EIP-1167 clone factory. | Unchanged. |

Assumed (per spec): each newspaper publishes one canonical truth and never emails
conflicting alerts. The threshold K exists so a single compromised newsroom email
pipeline can't settle a market alone. Known limitation: the signed **From, Subject and Date** are bound
by the header signature — Body-field conditions need the DKIM body-hash (`bh=`) check
(backlog A4). See the [backlog](docs/BACKLOG.md) for the full roadmap.
