# Backlog — road to Polymarket parity

Grounded in a source-level review of Polymarket's stack (Gnosis CTF, `ctf-exchange`,
`uma-ctf-adapter`, `neg-risk-ctf-adapter`) and its product UX. Our engine —
permissionless market creation + permissionless DKIM settlement — stays the
differentiator throughout; the backlog is everything around it.

Legend: **P0** = needed for any real deployment · **P1** = trading-experience parity
· **P2** = full product parity.

## A. Settlement engine (the DKIM core)

| # | Item | Notes |
|---|---|---|
| A1 **P0** | **DKIM verification** | Real RSA-SHA256 header verification, exact Subject/Date binding and empty-body enforcement. New registry restricts key authorization to the deploying registrar. Requires a fresh deployment to replace old verifier/registry clones. |
| A2 **P0** | **Authenticated DNS and historical keys** | Registrar authenticates domain/key associations today. Add DNSSEC verification and historical validity windows; arbitrary permissionless key registration is unsafe. |
| A3 | **ZK circuit experiment removed** | Public DKIM settlement is the product. No ZK dependencies, private-settlement path or trusted setup is required. Historical evaluation retained in docs/ZKEMAIL-PRIVATE-SETTLEMENT.md. |
| A4 **P1** | **Body-content binding** | Implemented on fresh Sepolia: complete `bh=` verification, bounded single-part body parsing and paginated uploads. Broader MIME, size/gas limits and proof compression remain in issues #1/#2; see BODY-PARSING.md. |
| A5 **P1** | **Settler incentive** | Creator-funded bounty paid to the address whose proof resolves the market (and to `resolveNo` caller), so settlement is economically automatic, like UMA proposer rewards. |
| A6 **P2** | **Dispute layer for oracle edge cases** | Spec assumes newspapers never publish conflicting emails. For parity with UMA's safety: optional escalation window where a bonded challenger can contest (e.g. claim the DKIM key leaked, or the email was retracted) before payouts finalize; escalates to a fallback oracle. |
| A7 **P2** | **Richer conditions** | Numeric captures with comparisons ("Fed cuts by `(\d+)` bps, ≥ 50"), NOT-conditions (market fails if a retraction email arrives), M-of-N across *different* regexes per source, time-ordered conditions ("A before B"). |

## B. Market/token layer

| # | Item | Notes |
|---|---|---|
| B1 **P1** | **Byte-compatible Gnosis CTF ids** | Adopt alt_bn128 collection derivation so positions are interoperable with deployed CTF tooling/indexers. |
| B2 **P1** | **NegRiskAdapter multi-outcome** | "Which paper reports it first?" / "Who wins the election?" — N linked binary conditions, wrapped collateral, NO-basket → YES conversions, exactly one YES. |
| B3 **P1** | **Proxy wallets + gasless UX** | Polymarket's relayer + proxy-wallet pattern (POLY_PROXY / Safe signature types) so users trade without holding gas. |
| B4 **P2** | **Collateral policy** | Per-market collateral is done; add fee-on-transfer/rebasing token guards, a curated collateral list in the UI, and native-token wrapping. |
| B5 **P2** | **Oracle-failure escape hatch** | If a market is unresolvable (all DKIM keys revoked mid-window), allow [1,1] 50/50 resolution after a long timeout so collateral is never stranded. |

## C. Trading venue

| # | Item | Notes |
|---|---|---|
| C1 **P1** | **CLOB (ctf-exchange port)** | EIP-712 signed orders, operator matching with MINT/MERGE/COMPLEMENTARY modes, onchain settlement, maker/taker fee schedule (symmetric `baseRate·min(p,1-p)`), nonce cancels. FPMM stays as bootstrap liquidity. |
| C2 **P1** | **Limit orders UI** | Price-in-cents + shares + expiration (GTC default), partial-fill disclosure, open-orders tab with cancel-all — Polymarket's exact grammar. |
| C3 **P2** | **Liquidity rewards** | LP incentive program (Polymarket's early FPMM rewards / current maker rebates). |

## D. Product & UX

| # | Item | Notes |
|---|---|---|
| D1 **P1** | **Price history charts** | Store trade events → chart with 1H/6H/1D/1W/1M/ALL tabs; display price = bid-ask midpoint (fallback last-trade when spread >10¢) once the CLOB exists. |
| D2 **P1** | **Real wallets** | RainbowKit/Privy via bread-ui-kit's `BreadUIKitProvider`/`LoginButton`/`Navbar` (the kit ships these; we currently use dev accounts). |
| D3 **P1** | **Portfolio depth** | Avg entry / Return (realized+unrealized) columns, history tab (Buy/Sell/Redeem/Split/Merge), P&L period filters, auto-redeem toggle. |
| D4 **P1** | **Resolution timeline UI** | Polymarket-style labeled timeline ("Proof 1/2 accepted → threshold reached → finalized"), plus an "email inbox" view rendering each accepted alert. |
| D5 **P2** | **Discovery** | ◑ *Categories shipped* (Polymarket-style category tags + filter tabs, stored as a description tag). Remaining: trending sort by 24h volume, comments, watchlists, embeds. |
| D6 **P2** | **Notifications** | Push/email when a tracked market gets a proof, resolves, or nears deadline. |
| D7 **P2** | **Settlement bot** | ✅ Sepolia automatic worker deployed: durable NYT IMAP intake, encrypted journal, restricted IPC signer, confirmed nonce retries and resumable body uploads. No automatic NO or key registration. Mainnet rollout and external health alert delivery remain; see AUTO-SETTLEMENT.md. |

## E. Infrastructure

| # | Item | Notes |
|---|---|---|
| E1 **P0** | **Gas reality pass** | Public RSA/DKIM settlement and onchain regex matching are the only regex settlement path. EIP-1167 clones reduce creation cost. Benchmark the new verifier and fees before deployment; historical ZK measurements are not settlement costs. |
| E2 **P0** | **Audit + invariant/fuzz suite** | The FPMM fee accounting and RegexLib parser are the two components most deserving adversarial review; add Foundry invariant campaigns (collateral conservation under random trade/fund/settle sequences). |
| E3 **P1** | **Indexer** | Subgraph/ponder for markets, trades, positions, volume — replaces the frontend's from-genesis log scans (fine on anvil, not on a real chain). |
| E4 **P2** | **Testnet + real-email dry run** | ◑ *Sepolia deployed + verified* (faucet TestUSDC, seeded markets, real NYT key; CI deploys per PR). Remaining: subscribe to the alert lists and settle a market with a real breaking-news email end to end. |

## September 2026 refactor

- Daily private mailbox index and trailing-14-day Polymarket coverage service: docs/DAILY-RESEARCH.md. Semantic review is separate from lexical retrieval.
- Platform fees (default 1% plus LP fee) implemented for new deployments: docs/FEES.md.
- Mailbox access and deployment migration are activation prerequisites: docs/EMAIL-ACCESS.md.

## Large email bodies and alternative execution (2026-09-10)

- **P1 — [#1: DKIM body size and gas limits](https://github.com/RonTuretzky/means-of-prediction/issues/1).** Measured direct-proof costs, 128 KiB relay policy, transaction gas cap, MIME/predicate bounds, pagination overhead, and succinct-proof alternatives. Local issue source: `docs/issues/email-body-size-and-cost.md`.
- **P1 — [#2: GasKiller body-settlement adapter](https://github.com/RonTuretzky/means-of-prediction/issues/2).** Proposed compact receipt with onchain RSA/header verification; current upstream input cap, operator trust and availability requirements, implementation stages and benchmark criteria. Tags `@tbsoc` and `@nomoregas`. Local issue source: `docs/issues/gaskiller-email-body-computation.md`.
