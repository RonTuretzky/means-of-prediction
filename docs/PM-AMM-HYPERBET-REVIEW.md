# PM-AMM and Hyperbet relevance

Reviewed 2026-09-09. This is a source-level integration assessment, not a deployed-contract audit. No external market was created, traded or settled.

Recommendation: explore a separate **static PM-AMM pool** while preserving this app's conditional tokens, DKIM resolver and collateral-denominated fee accounting. Keep the current FPMM as a benchmark. Hyperbet is useful reference material, but its contracts and template need substantial changes before they fit this application.

## Why the paper matters

Paradigm's curve allocates liquidity differently across probabilities under a Gaussian score model. The dynamic variant reduces liquidity toward expiry. Neither variant removes arbitrage losses or guarantees LP profitability. The authors explicitly distinguish gradual information flow from sudden events. That makes model fit uncertain for breaking-news email markets. [Paradigm paper](https://www.paradigm.xyz/writing/pm-amm).

For this app, compare candidate pools using the same collateral, fee rates and event histories. Measure executable quotes, slippage, LP ending wealth, platform revenue and gas separately. A platform fee pays the treasury; it does not reimburse LP losses. The current resolved-market/email dataset helps identify verifiable questions but does not contain the historical probability paths needed for an AMM profitability comparison.

## What the repositories actually provide

| Resource | Useful contribution | Integration gap |
| --- | --- | --- |
| NubsCarson/hyperbet-market | Agent command that creates a market and writes a static trading page; MIT-licensed template | Solana-specific; no general question-resolution service; pricing mismatch described below |
| PlayHyperia/hyperbet Solidity | Gaussian pricing, numerical swap solver, treasury configuration, deadline guards, router and tests | Different token and sell semantics; duel-specific oracle; settlement bypass path; mixed license markers |
| PlayHyperia/hyperbet Solana | Program-level curve math and oracle-account checks | Requires a matching fight-oracle duel result, not DKIM evidence |

Snapshots: [template `511d090`](https://github.com/NubsCarson/hyperbet-market/tree/511d0903a4d5c6b836ed2e953287e34ab2c089a4), [main repo `af354ce`](https://github.com/PlayHyperia/hyperbet/tree/af354ce3fad91e15b9db4f867d82b895c4a3d598). The latter's README lists launch and audit/remediation blockers; repository availability is not deployment verification.

## Concrete source findings

1. **The EVM settlement path can bypass its oracle.** `Router.proposerOutcome` is public. After the deadline a caller can post the bond with either result; `Router.settleMarket` exposes the market's five-minute finalization path, which sets RESOLVED and returns the bond without consulting `DuelOutcomeOracle`. A separate oracle-based path exists but is not required by that route. Adopting this lifecycle would undermine email-backed resolution. This conclusion follows the source call path; no live exploit was attempted. [Router](https://github.com/PlayHyperia/hyperbet/blob/af354ce3fad91e15b9db4f867d82b895c4a3d598/packages/evm-contracts/contracts/lvr_amm/Router.sol#L173), [market](https://github.com/PlayHyperia/hyperbet/blob/af354ce3fad91e15b9db4f867d82b895c4a3d598/packages/evm-contracts/contracts/lvr_amm/LvrMarket.sol#L107).

2. **An arbitrary prompt is not a settlement integration.** The template hashes the question into a duel key. The main Solana program requires a matching resolved/cancelled account owned by the configured fight-oracle program. The template's create/trade code supplies no process that establishes the answer for an arbitrary news question. Our DKIM resolver remains necessary. [Template creation](https://github.com/NubsCarson/hyperbet-market/blob/511d0903a4d5c6b836ed2e953287e34ab2c089a4/src/hyperbet.ts#L57), [oracle checks](https://github.com/PlayHyperia/hyperbet/blob/af354ce3fad91e15b9db4f867d82b895c4a3d598/packages/hyperbet-solana/anchor/programs/lvr_amm/src/instructions/settle_bet.rs#L65).

3. **The template displays the wrong marginal-price formula for its intended curve.** It displays `reserveNo / (reserveYes + reserveNo)`, while the core uses the Gaussian CDF of `(reserveNo - reserveYes) / liquidity`. An independent numerical check at an on-curve state with normalized reserve difference 1 gives **84.13%** from the curve and **92.86%** from the template formula. That reserve ratio is appropriate for our existing FPMM, but cannot carry over to PM-AMM. [Template UI](https://github.com/NubsCarson/hyperbet-market/blob/511d0903a4d5c6b836ed2e953287e34ab2c089a4/frontend/app.js#L79), [core pricing](https://github.com/PlayHyperia/hyperbet/blob/af354ce3fad91e15b9db4f867d82b895c4a3d598/packages/evm-contracts/contracts/lvr_amm/lib/Math.sol#L14).

4. **Dynamic mode needs independent numerical validation.** The template explicitly passes `false` and documents reserve exhaustion/overflow in short-expiry or small-liquidity cases. This is a report in its source, not an independently reproduced failure. Start with static mode; validate time units, liquidity initialization, rounding and near-expiry behavior before evaluating dynamic mode. [Template setting](https://github.com/NubsCarson/hyperbet-market/blob/511d0903a4d5c6b836ed2e953287e34ab2c089a4/src/hyperbet.ts#L83).

5. **Sell and fee semantics differ.** Hyperbet's EVM `sell` swaps into the opposite outcome token and burns the fee portion of input shares. It does not implement our FPMM's exact collateral payout with separate LP and platform collateral fees. Replacing the pool wholesale would change the trading UX and monetization. [Sell implementation](https://github.com/PlayHyperia/hyperbet/blob/af354ce3fad91e15b9db4f867d82b895c4a3d598/packages/evm-contracts/contracts/lvr_amm/LvrMarket.sol#L256).

6. **Check license scope before copying.** The small template is MIT. The main EVM Router and LvrMarket declare `UNLICENSED`; several math/token files say `SEE LICENSE IN LICENSE`. Those markers do not establish a uniform permissive grant for importing the stack. No code from these repositories was copied into the application.

## App-specific priorities

The current `FPMM.whileTrading` only checks whether a payout has been reported. It does not stop at the email deadline, so trading remains possible during the proof-submission buffer. Separating the trading cutoff from the evidence-submission window is a concrete protection to evaluate before changing the curve. Scheduled cutoffs cannot prevent every surprise-news jump, and a new AMM formula cannot authenticate an outcome.

Implement any experiment as a distinct pool type behind the same market condition and resolver. Preserve collateral sell/redemption semantics and separate treasury/LP entitlements. Compare identical trades at probabilities near 1%, 10%, 50%, 90% and 99%, small liquidity, abrupt announcements and impending expiry. Require quote/execution agreement, conservative rounding, collateral solvency, LP exit correctness and fee conservation. Then use the email research findings to select a few actual market types for a limited test deployment.
